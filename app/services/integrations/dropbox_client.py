"""
app/services/integrations/dropbox_client.py

Bloque 5.3 — Integración Dropbox

Flujo completo:
  1. El usuario inicia OAuth2 → GET /api/v1/integrations/dropbox/auth
  2. Dropbox redirige con ?code=... → GET /api/v1/integrations/dropbox/callback
  3. El token se guarda en la DB (modelo OAuthToken)
  4. El usuario lista sus archivos → GET /api/v1/integrations/dropbox/files
  5. El usuario importa un archivo → POST /api/v1/integrations/dropbox/import
     → descarga el archivo de Dropbox y lo encola en Celery igual que un upload normal

Scopes OAuth2 de Dropbox requeridos (configurar en la App Console):
  - files.metadata.read
  - files.content.read
  - account_info.read

Variables de entorno requeridas:
  DROPBOX_APP_KEY
  DROPBOX_APP_SECRET
  DROPBOX_REDIRECT_URI   (ej: https://tuapp.railway.app/api/v1/integrations/dropbox/callback)
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes OAuth2 Dropbox
# ─────────────────────────────────────────────────────────────────────────────

DROPBOX_AUTH_URL   = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL  = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_REVOKE_URL = "https://api.dropboxapi.com/2/auth/token/revoke"
DROPBOX_API        = "https://api.dropboxapi.com/2"
DROPBOX_CONTENT    = "https://content.dropboxapi.com/2"

# Extensiones que DocuFlow puede procesar
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf":  "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers OAuth2
# ─────────────────────────────────────────────────────────────────────────────

def build_auth_url(state: str) -> str:
    """
    Construye la URL de autorización de Dropbox OAuth2.
    `state` se valida en el callback para prevenir CSRF.
    """
    params = {
        "client_id":     settings.DROPBOX_APP_KEY,
        "redirect_uri":  settings.DROPBOX_REDIRECT_URI,
        "response_type": "code",
        "token_access_type": "offline",   # necesario para refresh_token
        "state":         state,
    }
    return f"{DROPBOX_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """
    Intercambia el authorization code por access_token + refresh_token.
    Retorna el JSON completo de la respuesta de Dropbox.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            DROPBOX_TOKEN_URL,
            data={
                "code":          code,
                "grant_type":    "authorization_code",
                "redirect_uri":  settings.DROPBOX_REDIRECT_URI,
            },
            auth=(settings.DROPBOX_APP_KEY, settings.DROPBOX_APP_SECRET),
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Obtiene un nuevo access_token usando el refresh_token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            DROPBOX_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "grant_type":    "refresh_token",
            },
            auth=(settings.DROPBOX_APP_KEY, settings.DROPBOX_APP_SECRET),
        )
        resp.raise_for_status()
        return resp.json()


async def revoke_token(access_token: str) -> None:
    """Revoca el token en el lado de Dropbox."""
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            DROPBOX_REVOKE_URL,
            headers={
                "Authorization":  f"Bearer {access_token}",
                "Content-Type":   "application/json",
            },
            content=b"null",
        )


# ─────────────────────────────────────────────────────────────────────────────
# API Dropbox
# ─────────────────────────────────────────────────────────────────────────────

async def list_dropbox_files(
    access_token: str,
    path: str = "",
    cursor: Optional[str] = None,
) -> dict:
    """
    Lista archivos de Dropbox filtrando solo extensiones soportadas.
    - path="" lista la raíz
    - Usa list_folder/continue para paginación con cursor

    Retorna { entries: [...], cursor, has_more }
    Cada entry incluye: id, name, path_lower, size, server_modified, docuflow_type
    """
    async with httpx.AsyncClient(timeout=20) as client:
        if cursor:
            resp = await client.post(
                f"{DROPBOX_API}/files/list_folder/continue",
                json={"cursor": cursor},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "application/json",
                },
            )
        else:
            resp = await client.post(
                f"{DROPBOX_API}/files/list_folder",
                json={
                    "path":                               path,
                    "recursive":                          False,
                    "include_media_info":                 False,
                    "include_deleted":                    False,
                    "include_has_explicit_shared_members": False,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "application/json",
                },
            )
        resp.raise_for_status()
        data = resp.json()

    # Filtrar solo archivos (no carpetas) con extensiones soportadas
    filtered = []
    for entry in data.get("entries", []):
        if entry.get(".tag") != "file":
            continue
        name = entry.get("name", "")
        ext  = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        doc_type = SUPPORTED_EXTENSIONS.get(ext)
        if doc_type:
            entry["docuflow_type"] = doc_type
            filtered.append(entry)

    return {
        "entries":  filtered,
        "cursor":   data.get("cursor"),
        "has_more": data.get("has_more", False),
    }


async def download_dropbox_file(
    access_token: str,
    path: str,
) -> tuple[bytes, str]:
    """
    Descarga un archivo de Dropbox por su path.
    Retorna (content_bytes, file_type_str).
    """
    import json as _json

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.post(
            f"{DROPBOX_CONTENT}/files/download",
            headers={
                "Authorization":   f"Bearer {access_token}",
                "Dropbox-API-Arg": _json.dumps({"path": path}),
            },
            content=b"",
        )
        resp.raise_for_status()

    name = path.rsplit("/", 1)[-1]
    ext  = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    file_type = SUPPORTED_EXTENSIONS.get(ext, "pdf")

    logger.info(
        "Dropbox download OK | path=%s | type=%s | bytes=%d",
        path, file_type, len(resp.content),
    )
    return resp.content, file_type


async def get_account_info(access_token: str) -> dict:
    """Obtiene info básica de la cuenta Dropbox conectada."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{DROPBOX_API}/users/get_current_account",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type":  "application/json",
            },
            content=b"null",
        )
        resp.raise_for_status()
        return resp.json()
