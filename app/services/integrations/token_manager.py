"""
app/services/integrations/token_manager.py

Bloque 5.3 — Gestión de tokens OAuth2 (guardar, refrescar, revocar).

Responsabilidades:
  - Guardar/actualizar tokens en DB después del callback OAuth2
  - Verificar si el access_token está expirado y refrescarlo automáticamente
  - Revocar tokens cuando el usuario desconecta la integración
  - Proveer get_valid_access_token(user_id, provider, db) para uso en routes
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.oauth_token import OAuthToken
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def save_token(
    *,
    db: Session,
    user_id: str,
    provider: str,
    token_data: dict,
    provider_email: Optional[str] = None,
    provider_name: Optional[str] = None,
) -> OAuthToken:
    """
    Crea o actualiza el OAuthToken para un usuario+proveedor.
    token_data es la respuesta JSON del endpoint de token del proveedor.
    """
    expires_in = token_data.get("expires_in")
    expires_at = (
        _utcnow() + timedelta(seconds=int(expires_in))
        if expires_in
        else None
    )

    existing = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
        .first()
    )

    if existing:
        existing.access_token   = token_data["access_token"]
        if token_data.get("refresh_token"):
            existing.refresh_token = token_data["refresh_token"]
        existing.token_type     = token_data.get("token_type", "Bearer")
        existing.scope          = token_data.get("scope")
        existing.expires_at     = expires_at
        existing.updated_at     = _utcnow()
        if provider_email:
            existing.provider_email = provider_email
        if provider_name:
            existing.provider_name = provider_name
        db.commit()
        db.refresh(existing)
        logger.info("OAuthToken actualizado | user=%s | provider=%s", user_id, provider)
        return existing
    else:
        token = OAuthToken(
            user_id        = user_id,
            provider       = provider,
            access_token   = token_data["access_token"],
            refresh_token  = token_data.get("refresh_token"),
            token_type     = token_data.get("token_type", "Bearer"),
            scope          = token_data.get("scope"),
            expires_at     = expires_at,
            provider_email = provider_email,
            provider_name  = provider_name,
        )
        db.add(token)
        db.commit()
        db.refresh(token)
        logger.info("OAuthToken creado | user=%s | provider=%s", user_id, provider)
        return token


async def get_valid_access_token(
    *,
    db: Session,
    user_id: str,
    provider: str,
) -> Optional[str]:
    """
    Retorna un access_token válido para el usuario+proveedor.
    Si está expirado, lo refresca automáticamente antes de devolverlo.
    Retorna None si el usuario no tiene el proveedor conectado.
    """
    token_row = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
        .first()
    )

    if not token_row:
        return None

    if token_row.is_expired():
        if not token_row.refresh_token:
            logger.warning(
                "Token expirado sin refresh_token | user=%s | provider=%s",
                user_id, provider,
            )
            # Eliminar el token inválido — el usuario deberá reconectar
            db.delete(token_row)
            db.commit()
            return None

        try:
            new_data = await _refresh(provider, token_row.refresh_token)
            save_token(
                db=db,
                user_id=user_id,
                provider=provider,
                token_data=new_data,
            )
            return new_data["access_token"]
        except Exception as exc:
            logger.error(
                "Error refrescando token | user=%s | provider=%s | error=%s",
                user_id, provider, exc,
            )
            return None

    return token_row.access_token


async def _refresh(provider: str, refresh_token: str) -> dict:
    """Llama al endpoint de refresh del proveedor correcto."""
    if provider == "google":
        from app.services.integrations.google_drive import refresh_access_token
        return await refresh_access_token(refresh_token)
    elif provider == "dropbox":
        from app.services.integrations.dropbox_client import refresh_access_token
        return await refresh_access_token(refresh_token)
    else:
        raise ValueError(f"Proveedor desconocido: {provider}")


def revoke_token(*, db: Session, user_id: str, provider: str) -> bool:
    """
    Revoca el token en el proveedor y lo elimina de la DB.
    Retorna True si había un token, False si no.
    """
    token_row = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
        .first()
    )
    if not token_row:
        return False

    # Revocar en el proveedor (best-effort, no fallar si hay error)
    import asyncio

    async def _do_revoke():
        try:
            if provider == "google":
                from app.services.integrations.google_drive import revoke_token as _rev
                await _rev(token_row.access_token)
            elif provider == "dropbox":
                from app.services.integrations.dropbox_client import revoke_token as _rev
                await _rev(token_row.access_token)
        except Exception as exc:
            logger.warning("Error revocando token en %s: %s", provider, exc)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # En contexto async (FastAPI endpoint)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(asyncio.run, _do_revoke())
        else:
            loop.run_until_complete(_do_revoke())
    except Exception:
        pass

    db.delete(token_row)
    db.commit()
    logger.info("OAuthToken revocado y eliminado | user=%s | provider=%s", user_id, provider)
    return True
