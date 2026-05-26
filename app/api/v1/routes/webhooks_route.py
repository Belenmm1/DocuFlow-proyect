"""
app/api/v1/routes/webhooks.py

Endpoints CRUD para gestión de webhooks del usuario autenticado.

Rutas:
  POST   /api/v1/webhooks            — crear webhook
  GET    /api/v1/webhooks            — listar los webhooks propios
  GET    /api/v1/webhooks/{id}       — detalle de un webhook
  PATCH  /api/v1/webhooks/{id}       — actualización parcial
  DELETE /api/v1/webhooks/{id}       — eliminar webhook
  POST   /api/v1/webhooks/{id}/test  — disparar un evento de prueba

Seguridad:
  - Todos los endpoints requieren JWT válido (get_current_user).
  - Un usuario solo puede ver/modificar sus propios webhooks.
  - El secret se genera en el servidor (secrets.token_hex) y se devuelve
    UNA SOLA VEZ en la respuesta de creación.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.webhook import WebhookConfig
from app.schemas.webhook import (
    WebhookCreate, WebhookUpdate,
    WebhookOut, WebhookCreated, WebhookList,
)
from app.core.dependencies import get_current_user
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# Máximo de webhooks por usuario (protección anti-spam)
MAX_WEBHOOKS_PER_USER = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_webhook_or_404(webhook_id: str, user: User, db: Session) -> WebhookConfig:
    """Obtiene un webhook verificando que pertenece al usuario actual."""
    wh = (
        db.query(WebhookConfig)
        .filter(
            WebhookConfig.id      == webhook_id,
            WebhookConfig.user_id == user.id,
        )
        .first()
    )
    if not wh:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook no encontrado.",
        )
    return wh


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=WebhookCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Crear webhook",
)
def create_webhook(
    body: WebhookCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WebhookCreated:
    """
    Registra un nuevo webhook para el usuario autenticado.

    El `secret` se genera aleatoriamente (32 bytes hex = 64 chars) y se
    devuelve **una sola vez** en esta respuesta. Guardalo de inmediato;
    no hay forma de recuperarlo después (solo regenerarlo eliminando y
    recreando el webhook).

    Usá el secret para verificar la firma `X-DocuFlow-Signature` que
    DocuFlow incluirá en cada request saliente:

    ```
    X-DocuFlow-Signature: sha256=<HMAC-SHA256(secret, body)>
    ```
    """
    # Límite de webhooks por usuario
    count = (
        db.query(WebhookConfig)
        .filter(WebhookConfig.user_id == current_user.id)
        .count()
    )
    if count >= MAX_WEBHOOKS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Límite de {MAX_WEBHOOKS_PER_USER} webhooks por usuario alcanzado.",
        )

    raw_secret = secrets.token_hex(32)   # 64 caracteres hex

    wh = WebhookConfig(
        user_id   = current_user.id,
        url       = str(body.url),
        events    = [e.value for e in body.events],
        secret    = raw_secret,
        is_active = body.is_active,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)

    logger.info(
        "Webhook creado | user_id=%s | webhook_id=%s | events=%s",
        current_user.id, wh.id, wh.events,
    )

    # Adjuntamos el secret en texto plano SOLO en esta respuesta
    return WebhookCreated(
        id         = wh.id,
        url        = wh.url,
        events     = wh.events,
        is_active  = wh.is_active,
        created_at = wh.created_at,
        updated_at = wh.updated_at,
        secret     = raw_secret,
    )


@router.get(
    "/",
    response_model=WebhookList,
    summary="Listar webhooks propios",
)
def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WebhookList:
    """Devuelve todos los webhooks registrados por el usuario autenticado."""
    items = (
        db.query(WebhookConfig)
        .filter(WebhookConfig.user_id == current_user.id)
        .order_by(WebhookConfig.created_at.desc())
        .all()
    )
    return WebhookList(total=len(items), items=items)


@router.get(
    "/{webhook_id}",
    response_model=WebhookOut,
    summary="Detalle de webhook",
)
def get_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WebhookOut:
    return _get_webhook_or_404(webhook_id, current_user, db)


@router.patch(
    "/{webhook_id}",
    response_model=WebhookOut,
    summary="Actualizar webhook",
)
def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WebhookOut:
    """
    Actualización parcial — solo se modifican los campos presentes en el body.
    Permite activar/desactivar, cambiar URL o reasignar eventos sin recrear.
    """
    wh = _get_webhook_or_404(webhook_id, current_user, db)

    if body.url is not None:
        wh.url = str(body.url)
    if body.events is not None:
        wh.events = [e.value for e in body.events]
    if body.is_active is not None:
        wh.is_active = body.is_active

    db.commit()
    db.refresh(wh)

    logger.info(
        "Webhook actualizado | user_id=%s | webhook_id=%s",
        current_user.id, wh.id,
    )
    return wh


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar webhook",
)
def delete_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    wh = _get_webhook_or_404(webhook_id, current_user, db)
    db.delete(wh)
    db.commit()
    logger.info(
        "Webhook eliminado | user_id=%s | webhook_id=%s",
        current_user.id, webhook_id,
    )


@router.post(
    "/{webhook_id}/test",
    summary="Disparar evento de prueba",
    status_code=status.HTTP_202_ACCEPTED,
)
async def test_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Envía un payload de prueba al endpoint configurado para verificar
    conectividad y firma.

    El payload usa `event: "webhook.test"` para distinguirlo de eventos reales.
    Devuelve el HTTP status code recibido por el endpoint destino.
    """
    from app.services.webhook_dispatcher import dispatch_webhook

    wh = _get_webhook_or_404(webhook_id, current_user, db)

    if not wh.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El webhook está desactivado. Activalo antes de hacer la prueba.",
        )

    test_payload = {
        "event":      "webhook.test",
        "webhook_id": wh.id,
        "message":    "Este es un evento de prueba enviado desde DocuFlow.",
    }

    result = await dispatch_webhook(wh, test_payload)

    logger.info(
        "Webhook test | user_id=%s | webhook_id=%s | status=%s",
        current_user.id, wh.id, result.get("status_code"),
    )

    return {
        "webhook_id":  wh.id,
        "url":         wh.url,
        "status_code": result.get("status_code"),
        "success":     result.get("success", False),
        "error":       result.get("error"),
    }
