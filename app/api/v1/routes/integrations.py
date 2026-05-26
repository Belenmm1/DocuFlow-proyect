"""
app/api/v1/routes/integrations.py

Bloque 5.3 — Endpoints de integración con Google Drive y Dropbox

Rutas Google Drive:
  GET  /api/v1/integrations/google/auth              → URL de autorización OAuth2
  GET  /api/v1/integrations/google/callback          → Callback OAuth2 (redirect de Google)
  GET  /api/v1/integrations/google/status            → Estado de conexión
  GET  /api/v1/integrations/google/files             → Listar archivos del Drive
  POST /api/v1/integrations/google/import/{file_id}  → Importar un archivo a DocuFlow
  DELETE /api/v1/integrations/google/disconnect      → Desconectar cuenta

Rutas Dropbox:
  GET  /api/v1/integrations/dropbox/auth             → URL de autorización OAuth2
  GET  /api/v1/integrations/dropbox/callback         → Callback OAuth2 (redirect de Dropbox)
  GET  /api/v1/integrations/dropbox/status           → Estado de conexión
  GET  /api/v1/integrations/dropbox/files            → Listar archivos
  POST /api/v1/integrations/dropbox/import           → Importar un archivo a DocuFlow
  DELETE /api/v1/integrations/dropbox/disconnect     → Desconectar cuenta

General:
  GET  /api/v1/integrations/status                   → Estado de todas las integraciones
"""

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.models.database import Document, DocumentStatus, get_db
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.services.integrations import google_drive, dropbox_client
from app.services.integrations.token_manager import (
    get_valid_access_token,
    revoke_token,
    save_token,
)
from app.utils.file_handler import FileHandler, validate_file
from app.workers.tasks import process_document
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])
file_handler = FileHandler()

# ─────────────────────────────────────────────────────────────────────────────
# Schemas de respuesta
# ─────────────────────────────────────────────────────────────────────────────

class IntegrationStatus(BaseModel):
    connected: bool
    provider_email: Optional[str] = None
    provider_name: Optional[str] = None


class AllIntegrationsStatus(BaseModel):
    google: IntegrationStatus
    dropbox: IntegrationStatus


class DriveFileItem(BaseModel):
    id: str
    name: str
    mimeType: str
    size: Optional[str] = None
    modifiedTime: Optional[str] = None
    webViewLink: Optional[str] = None
    docuflow_type: Optional[str] = None


class DriveFilesResponse(BaseModel):
    files: list[DriveFileItem]
    next_page_token: Optional[str] = None


class DropboxFileItem(BaseModel):
    id: str
    name: str
    path_lower: str
    size: Optional[int] = None
    server_modified: Optional[str] = None
    docuflow_type: Optional[str] = None


class DropboxFilesResponse(BaseModel):
    entries: list[DropboxFileItem]
    cursor: Optional[str] = None
    has_more: bool = False


class ImportResponse(BaseModel):
    doc_id: int
    filename: str
    status: str
    task_id: str


class DropboxImportBody(BaseModel):
    path: str   # path completo en Dropbox, ej: "/documentos/contrato.pdf"


# ─────────────────────────────────────────────────────────────────────────────
# Estado general
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=AllIntegrationsStatus, summary="Estado de todas las integraciones")
def all_integrations_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AllIntegrationsStatus:
    """Muestra si el usuario tiene Google Drive y/o Dropbox conectados."""
    def _get_status(provider: str) -> IntegrationStatus:
        row = (
            db.query(OAuthToken)
            .filter(OAuthToken.user_id == current_user.id, OAuthToken.provider == provider)
            .first()
        )
        if not row:
            return IntegrationStatus(connected=False)
        return IntegrationStatus(
            connected=True,
            provider_email=row.provider_email,
            provider_name=row.provider_name,
        )

    return AllIntegrationsStatus(
        google=_get_status("google"),
        dropbox=_get_status("dropbox"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE DRIVE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/google/auth", summary="Iniciar OAuth2 con Google Drive")
async def google_auth(
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Retorna la URL de autorización de Google Drive.
    El frontend debe redirigir al usuario a esa URL.

    El `state` codifica el user_id de forma segura para validarlo en el callback.
    """
    _check_google_configured()

    # state = "<user_id>:<nonce>" firmado con un prefijo secreto
    nonce = secrets.token_urlsafe(16)
    state = f"{current_user.id}:{nonce}"

    auth_url = google_drive.build_auth_url(state=state)
    return {"auth_url": auth_url, "provider": "google"}


@router.get("/google/callback", summary="Callback OAuth2 Google (no llamar directamente)")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Google redirige aquí con el authorization code.
    Intercambia el code por tokens y los guarda en DB.
    Redirige al frontend con ?connected=true o ?error=...
    """
    _check_google_configured()

    # Extraer user_id del state
    try:
        user_id, _nonce = state.split(":", 1)
    except ValueError:
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?provider=google&error=invalid_state"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?provider=google&error=user_not_found"
        )

    try:
        token_data = await google_drive.exchange_code_for_tokens(code)
    except Exception as exc:
        logger.error("Google OAuth error: %s", exc)
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?provider=google&error=token_exchange_failed"
        )

    # Obtener email de la cuenta conectada
    provider_email = None
    provider_name  = None
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            if resp.status_code == 200:
                info = resp.json()
                provider_email = info.get("email")
                provider_name  = info.get("name")
    except Exception:
        pass

    save_token(
        db=db,
        user_id=user_id,
        provider="google",
        token_data=token_data,
        provider_email=provider_email,
        provider_name=provider_name,
    )

    logger.info("Google Drive conectado | user=%s | email=%s", user_id, provider_email)
    return RedirectResponse(
        url=f"{settings.APP_URL}/settings/integrations?provider=google&connected=true"
    )


@router.get("/google/status", response_model=IntegrationStatus, summary="Estado Google Drive")
def google_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntegrationStatus:
    row = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == current_user.id, OAuthToken.provider == "google")
        .first()
    )
    if not row:
        return IntegrationStatus(connected=False)
    return IntegrationStatus(
        connected=True,
        provider_email=row.provider_email,
        provider_name=row.provider_name,
    )


@router.get("/google/files", response_model=DriveFilesResponse, summary="Listar archivos de Google Drive")
async def google_list_files(
    page_token: Optional[str] = Query(default=None),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DriveFilesResponse:
    """
    Lista archivos de Google Drive del usuario, filtrando solo PDF, DOCX y XLSX
    (incluyendo Google Docs y Google Sheets nativos, que se exportan automáticamente).
    """
    _check_google_configured()
    access_token = await _require_google_token(current_user.id, db)

    try:
        data = await google_drive.list_drive_files(
            access_token,
            page_token=page_token,
            page_size=page_size,
        )
    except Exception as exc:
        logger.error("Error listando Drive | user=%s | error=%s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al consultar Google Drive: {exc}",
        )

    return DriveFilesResponse(
        files=[DriveFileItem(**f) for f in data.get("files", [])],
        next_page_token=data.get("nextPageToken"),
    )


@router.post(
    "/google/import/{file_id}",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Importar archivo de Google Drive",
)
async def google_import_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResponse:
    """
    Descarga el archivo indicado de Google Drive y lo procesa igual que un upload normal.
    Retorna 202 Accepted con el doc_id para polling de estado.
    """
    _check_google_configured()
    access_token = await _require_google_token(current_user.id, db)

    # Obtener metadatos del archivo
    try:
        meta = await google_drive.get_file_metadata(access_token, file_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error obteniendo metadatos del archivo: {exc}",
        )

    mime_type = meta.get("mimeType", "")
    filename  = meta.get("name", f"drive_{file_id}")

    if mime_type not in google_drive.SUPPORTED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo de archivo no soportado: {mime_type}",
        )

    # Descargar contenido
    try:
        content, file_type = await google_drive.download_drive_file(
            access_token, file_id, mime_type
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error descargando el archivo de Drive: {exc}",
        )

    return await _create_document_from_bytes(
        content=content,
        filename=_ensure_extension(filename, file_type),
        file_type=file_type,
        user_id=current_user.id,
        db=db,
    )


@router.delete("/google/disconnect", status_code=status.HTTP_204_NO_CONTENT, summary="Desconectar Google Drive")
def google_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Revoca el token y elimina la conexión con Google Drive."""
    revoke_token(db=db, user_id=current_user.id, provider="google")


# ─────────────────────────────────────────────────────────────────────────────
# DROPBOX
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dropbox/auth", summary="Iniciar OAuth2 con Dropbox")
async def dropbox_auth(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Retorna la URL de autorización de Dropbox."""
    _check_dropbox_configured()

    nonce = secrets.token_urlsafe(16)
    state = f"{current_user.id}:{nonce}"
    auth_url = dropbox_client.build_auth_url(state=state)
    return {"auth_url": auth_url, "provider": "dropbox"}


@router.get("/dropbox/callback", summary="Callback OAuth2 Dropbox (no llamar directamente)")
async def dropbox_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """Dropbox redirige aquí tras la autorización."""
    _check_dropbox_configured()

    try:
        user_id, _nonce = state.split(":", 1)
    except ValueError:
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?provider=dropbox&error=invalid_state"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?provider=dropbox&error=user_not_found"
        )

    try:
        token_data = await dropbox_client.exchange_code_for_tokens(code)
    except Exception as exc:
        logger.error("Dropbox OAuth error: %s", exc)
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?provider=dropbox&error=token_exchange_failed"
        )

    # Obtener info de la cuenta
    provider_email = None
    provider_name  = None
    try:
        info = await dropbox_client.get_account_info(token_data["access_token"])
        provider_email = info.get("email")
        name_obj = info.get("name", {})
        provider_name = name_obj.get("display_name")
    except Exception:
        pass

    save_token(
        db=db,
        user_id=user_id,
        provider="dropbox",
        token_data=token_data,
        provider_email=provider_email,
        provider_name=provider_name,
    )

    logger.info("Dropbox conectado | user=%s | email=%s", user_id, provider_email)
    return RedirectResponse(
        url=f"{settings.APP_URL}/settings/integrations?provider=dropbox&connected=true"
    )


@router.get("/dropbox/status", response_model=IntegrationStatus, summary="Estado Dropbox")
def dropbox_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntegrationStatus:
    row = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == current_user.id, OAuthToken.provider == "dropbox")
        .first()
    )
    if not row:
        return IntegrationStatus(connected=False)
    return IntegrationStatus(
        connected=True,
        provider_email=row.provider_email,
        provider_name=row.provider_name,
    )


@router.get("/dropbox/files", response_model=DropboxFilesResponse, summary="Listar archivos de Dropbox")
async def dropbox_list_files(
    path: str = Query(default="", description='Ruta en Dropbox. Raíz = "" o "/"'),
    cursor: Optional[str] = Query(default=None, description="Cursor de paginación"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DropboxFilesResponse:
    """
    Lista archivos de Dropbox filtrando solo PDF, DOCX y XLSX.
    Usa `cursor` para paginar (viene en la respuesta cuando `has_more=true`).
    """
    _check_dropbox_configured()
    access_token = await _require_dropbox_token(current_user.id, db)

    # Normalizar path vacío
    normalized_path = "" if path in ("", "/") else path

    try:
        data = await dropbox_client.list_dropbox_files(
            access_token,
            path=normalized_path,
            cursor=cursor,
        )
    except Exception as exc:
        logger.error("Error listando Dropbox | user=%s | error=%s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al consultar Dropbox: {exc}",
        )

    return DropboxFilesResponse(
        entries=[DropboxFileItem(**e) for e in data.get("entries", [])],
        cursor=data.get("cursor"),
        has_more=data.get("has_more", False),
    )


@router.post(
    "/dropbox/import",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Importar archivo de Dropbox",
)
async def dropbox_import_file(
    body: DropboxImportBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResponse:
    """
    Descarga el archivo del path de Dropbox indicado y lo procesa en DocuFlow.
    """
    _check_dropbox_configured()
    access_token = await _require_dropbox_token(current_user.id, db)

    try:
        content, file_type = await dropbox_client.download_dropbox_file(
            access_token, body.path
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error descargando el archivo de Dropbox: {exc}",
        )

    filename = body.path.rsplit("/", 1)[-1]
    return await _create_document_from_bytes(
        content=content,
        filename=filename,
        file_type=file_type,
        user_id=current_user.id,
        db=db,
    )


@router.delete("/dropbox/disconnect", status_code=status.HTTP_204_NO_CONTENT, summary="Desconectar Dropbox")
def dropbox_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Revoca el token y elimina la conexión con Dropbox."""
    revoke_token(db=db, user_id=current_user.id, provider="dropbox")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _check_google_configured() -> None:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La integración con Google Drive no está configurada en este servidor.",
        )


def _check_dropbox_configured() -> None:
    if not settings.DROPBOX_APP_KEY or not settings.DROPBOX_APP_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La integración con Dropbox no está configurada en este servidor.",
        )


async def _require_google_token(user_id: str, db: Session) -> str:
    token = await get_valid_access_token(db=db, user_id=user_id, provider="google")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Drive no está conectado. Conectalo primero en /integrations/google/auth.",
        )
    return token


async def _require_dropbox_token(user_id: str, db: Session) -> str:
    token = await get_valid_access_token(db=db, user_id=user_id, provider="dropbox")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dropbox no está conectado. Conectalo primero en /integrations/dropbox/auth.",
        )
    return token


async def _create_document_from_bytes(
    *,
    content: bytes,
    filename: str,
    file_type: str,
    user_id: str,
    db: Session,
) -> ImportResponse:
    """
    Valida, guarda y encola el documento igual que el endpoint de upload normal.
    Reutiliza FileHandler para consistencia con el resto del sistema.
    """
    # Límite de tamaño (usa el plan del usuario si está disponible, default 20MB)
    max_mb = settings.MAX_FILE_SIZE_MB
    validate_file(content, file_type, max_mb=max_mb)

    # Guardar en disco
    import uuid as _uuid
    tmp_id = str(_uuid.uuid4())
    file_path = file_handler.save_bytes(content, tmp_id, file_type)

    doc = Document(
        filename  = filename,
        file_path = file_path,
        file_type = file_type,
        file_size = len(content),
        status    = DocumentStatus.PENDING,
        user_id   = user_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    task = process_document.delay(doc.id)
    doc.task_id = task.id
    db.commit()
    db.refresh(doc)

    logger.info(
        "Documento importado | user=%s | doc_id=%s | filename=%s | type=%s",
        user_id, doc.id, filename, file_type,
    )

    return ImportResponse(
        doc_id=doc.id,
        filename=doc.filename,
        status=doc.status.value,
        task_id=doc.task_id,
    )


def _ensure_extension(filename: str, file_type: str) -> str:
    """Asegura que el filename tenga la extensión correcta."""
    ext_map = {"pdf": ".pdf", "docx": ".docx", "xlsx": ".xlsx"}
    expected_ext = ext_map.get(file_type, f".{file_type}")
    if not filename.lower().endswith(expected_ext):
        # Quitar extensión anterior si tiene y agregar la correcta
        base = filename.rsplit(".", 1)[0] if "." in filename else filename
        return f"{base}{expected_ext}"
    return filename
