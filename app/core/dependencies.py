"""
app/core/dependencies.py

Bloque 6.2 — Autenticación dual: JWT Bearer + X-API-Key header.

get_current_user acepta cualquiera de los dos métodos:
  1. Authorization: Bearer <jwt>
  2. X-API-Key: df_live_<...>

Los límites y permisos son los del plan del usuario propietario de la clave.
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.core.api_key_utils import hash_key
from app.models.database import get_db
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)   # auto_error=False → no falla si falta


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency unificada: acepta JWT Bearer o X-API-Key.
    Prioridad: JWT > API Key.
    """
    # ── 1. JWT Bearer ──────────────────────────────────────────────────────
    if credentials is not None:
        token   = credentials.credentials
        payload = decode_token(token)

        if payload is None or payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido o expirado.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id: str = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()

        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado o inactivo.",
            )
        return user

    # ── 2. X-API-Key header ────────────────────────────────────────────────
    if x_api_key is not None:
        return _auth_via_api_key(x_api_key, db)

    # ── 3. Sin credenciales ────────────────────────────────────────────────
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Se requiere autenticación (Bearer token o X-API-Key).",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _auth_via_api_key(raw_key: str, db: Session) -> User:
    """Verifica X-API-Key y devuelve el usuario propietario."""
    from app.models.api_key import APIKey

    key_hash = hash_key(raw_key)
    api_key  = db.query(APIKey).filter(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True,          # noqa: E712
    ).first()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida o revocada.",
        )

    # Verificar expiración
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key expirada.",
        )

    # Actualizar last_used_at (best-effort, no rompe si falla)
    try:
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()

    user = db.query(User).filter(User.id == api_key.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario propietario de la API Key no encontrado o inactivo.",
        )
    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador.",
        )
    return current_user
