"""
app/services/integrations/google_drive.py

Bloque 5.3 — Integración Google Drive

Flujo completo:
  1. El usuario inicia OAuth2 → GET /api/v1/integrations/google/auth
  2. Google redirige con ?code=... → GET /api/v1/integrations/google/callback
  3. El token se guarda en la DB (modelo OAuthToken)
  4. El usuario lista sus archivos → GET /api/v1/integrations/google/files
  5. El usuario importa un archivo → POST /api/v1/integrations/google/import/{file_id}
     → descarga el archivo de Drive y lo encola en Celery igual que un upload normal

Scopes usados:
  - https://www.googleapis.com/auth/drive.readonly
    (solo lectura: lista y descarga archivos, no escribe en Drive)

Variables de entorno requeridas:
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI   (ej: https://tuapp.railway.app/api/v1/integrations/google/callback)
"""

from __future__ import annotations

import io
import urllib.parse
from typing import Optional

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes OAuth2
# ─────────────────────────────────────────────────────────────────────────────

GOOGLE_AUTH_URL    = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL   = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL  = "https://oauth2.googleapis.com/revoke"
GOOGLE_DRIVE_API   = "https://www.googleapis.com/drive/v3"

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "openid",
    "email",
]

# Tipos MIME que DocuFlow puede procesar
SUPPORTED_MIME_TYPES = {
    "application/pdf":  "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    # Google Docs nativos → exportar como DOCX
    "application/vnd.google-apps.document":     "docx",
    # Google Sheets nativos → exportar como XLSX
    "application/vnd.google-apps.spreadsheet":  "xlsx",
}

# MIMEs de exportación para Google Docs nativos
GOOGLE_EXPORT_MIME = {
    "application/vnd.google-apps.document":    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers OAuth2
# ─────────────────────────────────────────────────────────────────────────────

def build_auth_url(state: str) -> str:
    """
    Construye la URL de autorización de Google OAuth2.
    `state` debe ser un token opaco y seguro que identifica al usuario
    (se valida en el callback para prevenir CSRF).
    """
    params = {
        "client_id":     settings.GOOGLE_CLIENT_ID,
        "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(DRIVE_SCOPES),
        "access_type":   "offline",   # necesario para obtener refresh_token
        "prompt":        "consent",   # fuerza la entrega del refresh_token
        "state":         state,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """
    Intercambia el authorization code por access_token + refresh_token.
    Retorna el JSON completo de la respuesta de Google.
    Lanza httpx.HTTPStatusError si Google responde con error.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code":          code,
                "client_id":     settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """
    Obtiene un nuevo access_token usando el refresh_token guardado.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id":     settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "grant_type":    "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def revoke_token(token: str) -> None:
    """Revoca un token (access o refresh) en el lado de Google."""
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(GOOGLE_REVOKE_URL, params={"token": token})


# ─────────────────────────────────────────────────────────────────────────────
# API Drive
# ─────────────────────────────────────────────────────────────────────────────

async def list_drive_files(
    access_token: str,
    page_token: Optional[str] = None,
    page_size: int = 20,
) -> dict:
    """
    Lista archivos del Drive del usuario filtrando solo los tipos soportados.
    Retorna { files: [...], nextPageToken: ... }

    Cada archivo incluye: id, name, mimeType, size, modifiedTime, webViewLink
    """
    # Construir query para filtrar solo tipos soportados
    mime_filter = " or ".join(
        f"mimeType='{m}'" for m in SUPPORTED_MIME_TYPES
    )
    query = f"trashed=false and ({mime_filter})"

    params: dict = {
        "q":        query,
        "pageSize": page_size,
        "fields":   "nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink)",
        "orderBy":  "modifiedTime desc",
    }
    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{GOOGLE_DRIVE_API}/files",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()

    # Agregar campo docuflow_type para que el frontend sepa qué puede importar
    for f in data.get("files", []):
        f["docuflow_type"] = SUPPORTED_MIME_TYPES.get(f.get("mimeType", ""), None)

    return data


async def download_drive_file(
    access_token: str,
    file_id: str,
    mime_type: str,
) -> tuple[bytes, str]:
    """
    Descarga un archivo de Drive.
    - Para archivos nativos de Google (Docs/Sheets): usa la API de exportación.
    - Para binarios (PDF, DOCX, XLSX): usa el endpoint de descarga directa.

    Retorna (content_bytes, file_type_str).
    """
    is_google_native = mime_type in GOOGLE_EXPORT_MIME

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        if is_google_native:
            export_mime = GOOGLE_EXPORT_MIME[mime_type]
            resp = await client.get(
                f"{GOOGLE_DRIVE_API}/files/{file_id}/export",
                params={"mimeType": export_mime},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            file_type = SUPPORTED_MIME_TYPES[mime_type]
        else:
            resp = await client.get(
                f"{GOOGLE_DRIVE_API}/files/{file_id}",
                params={"alt": "media"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            file_type = SUPPORTED_MIME_TYPES.get(mime_type, "pdf")

        resp.raise_for_status()

    logger.info(
        "Google Drive download OK | file_id=%s | type=%s | bytes=%d",
        file_id, file_type, len(resp.content),
    )
    return resp.content, file_type


async def get_file_metadata(access_token: str, file_id: str) -> dict:
    """Obtiene metadatos de un archivo específico de Drive."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{GOOGLE_DRIVE_API}/files/{file_id}",
            params={"fields": "id,name,mimeType,size,modifiedTime"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
