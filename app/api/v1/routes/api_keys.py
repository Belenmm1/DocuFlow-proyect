"""
app/api/v1/routes/api_keys.py

Bloque 6.2 — Endpoints de gestión de API Keys.

Rutas:
  POST   /api-keys              → crear clave (solo Pro/Enterprise)
  GET    /api-keys              → listar claves del usuario
  DELETE /api-keys/{key_id}     → revocar clave
  PATCH  /api-keys/{key_id}     → activar / desactivar / renombrar
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.limiter import limiter
from app.core.plan_limits import get_plan_config, require_api_keys
from app.core.api_key_utils import generate_api_key
from app.models.api_key import APIKey
from app.models.database import get_db
from app.models.user import User
from app.utils.logger import get_logger

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    expires_at: Optional[datetime] = None     # None = sin expiración


class APIKeyCreatedResponse(BaseModel):
    """Solo se devuelve la clave en claro en este único response."""
    id: str
    name: str
    key: str                                  # ← valor completo, mostrar UNA SOLA VEZ
    key_prefix: str
    expires_at: Optional[datetime] = None
    created_at: datetime


class APIKeyOut(BaseModel):
    """Listado — nunca incluye el valor en claro."""
    id: str
    name: str
    description: Optional[str] = None
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_api_key(
    request: Request,
    body: APIKeyCreate,
    current_user: User = Depends(require_api_keys),   # bloquea plan Free
    db: Session = Depends(get_db),
):
    """
    Crea una nueva API Key para el usuario autenticado.
    **El valor en claro solo se devuelve en este response — no se puede recuperar después.**
    """
    config = get_plan_config(current_user.plan)

    # Verificar límite de claves por plan
    active_count = (
        db.query(APIKey)
        .filter(APIKey.user_id == current_user.id, APIKey.is_active == True)  # noqa: E712
        .count()
    )
    if active_count >= config.max_api_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Límite de API Keys alcanzado para el plan '{current_user.plan.value}' "
                f"({config.max_api_keys} claves activas). "
                "Revocá una existente o actualizá tu plan."
            ),
        )

    # Validar expiración
    if body.expires_at and body.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de expiración debe ser futura.",
        )

    raw_key, key_hash, key_prefix = generate_api_key()

    api_key = APIKey(
        id          = str(uuid.uuid4()),
        key_hash    = key_hash,
        key_prefix  = key_prefix,
        name        = body.name.strip(),
        description = body.description,
        user_id     = current_user.id,
        expires_at  = body.expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info("API Key creada | user=%s key_id=%s prefix=%s",
                current_user.id, api_key.id, key_prefix)

    return APIKeyCreatedResponse(
        id         = api_key.id,
        name       = api_key.name,
        key        = raw_key,           # ← único momento en que se expone
        key_prefix = key_prefix,
        expires_at = api_key.expires_at,
        created_at = api_key.created_at,
    )


@router.get("", response_model=list[APIKeyOut])
def list_api_keys(
    current_user: User = Depends(require_api_keys),
    db: Session = Depends(get_db),
):
    """Lista todas las API Keys del usuario (activas e inactivas)."""
    keys = (
        db.query(APIKey)
        .filter(APIKey.user_id == current_user.id)
        .order_by(APIKey.created_at.desc())
        .all()
    )
    return keys


@router.patch("/{key_id}", response_model=APIKeyOut)
def update_api_key(
    key_id: str,
    body: APIKeyPatch,
    current_user: User = Depends(require_api_keys),
    db: Session = Depends(get_db),
):
    """Renombra, activa o desactiva una API Key."""
    api_key = _get_own_key(key_id, current_user.id, db)

    if body.name is not None:
        api_key.name = body.name.strip()
    if body.description is not None:
        api_key.description = body.description
    if body.is_active is not None:
        api_key.is_active = body.is_active

    db.commit()
    db.refresh(api_key)
    logger.info("API Key actualizada | user=%s key_id=%s", current_user.id, key_id)
    return api_key


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    current_user: User = Depends(require_api_keys),
    db: Session = Depends(get_db),
):
    """Revoca (elimina) una API Key permanentemente."""
    api_key = _get_own_key(key_id, current_user.id, db)
    db.delete(api_key)
    db.commit()
    logger.info("API Key revocada | user=%s key_id=%s", current_user.id, key_id)


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _get_own_key(key_id: str, user_id: str, db: Session) -> APIKey:
    key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == user_id,
    ).first()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key no encontrada.",
        )
    return key
