"""
app/api/v1/routes/billing.py

Bloque 6.1 — Endpoints de billing con Stripe.

Rutas:
  POST /billing/checkout          → inicia suscripción (checkout session)
  POST /billing/portal            → abre Customer Portal (gestionar/cancelar)
  GET  /billing/subscription      → estado de suscripción del usuario
  POST /billing/cancel            → cancela al final del período
  POST /billing/webhook           → recibe eventos de Stripe (sin auth JWT)
"""

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.limiter import limiter
from app.models.database import get_db
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User
from app.services.stripe_service import (
    create_checkout_session,
    create_portal_session,
    handle_stripe_webhook,
)
from app.utils.logger import get_logger

router = APIRouter(prefix="/billing", tags=["billing"])
logger = get_logger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "enterprise"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


class SubscriptionOut(BaseModel):
    plan: str
    status: str
    stripe_subscription_id: str | None = None
    current_period_end: str | None = None
    cancel_at_period_end: bool = False

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/checkout", response_model=CheckoutResponse, status_code=200)
@limiter.limit("10/minute")
def checkout(
    request: Request,
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Inicia el flujo de suscripción con Stripe Checkout.
    Devuelve la URL a la que redirigir al usuario.
    """
    if body.plan not in ("pro", "enterprise"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan inválido. Opciones: pro, enterprise.",
        )

    if current_user.plan.value == body.plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya estás en el plan {body.plan}.",
        )

    try:
        url = create_checkout_session(current_user, body.plan, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except stripe.error.StripeError as exc:
        logger.error("Stripe error en checkout | user=%s error=%s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al crear la sesión de pago. Intentá de nuevo.",
        )

    return CheckoutResponse(checkout_url=url)


@router.post("/portal", response_model=PortalResponse, status_code=200)
@limiter.limit("10/minute")
def portal(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Abre el Customer Portal de Stripe para gestionar o cancelar la suscripción.
    Solo disponible para usuarios con suscripción activa.
    """
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()

    if not sub or not sub.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenés una suscripción activa para gestionar.",
        )

    try:
        url = create_portal_session(current_user, db)
    except stripe.error.StripeError as exc:
        logger.error("Stripe error en portal | user=%s error=%s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al abrir el portal de facturación.",
        )

    return PortalResponse(portal_url=url)


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el estado de suscripción del usuario autenticado."""
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()

    if not sub:
        # Usuario free sin fila en subscriptions
        return SubscriptionOut(plan="free", status="active")

    return SubscriptionOut(
        plan=sub.plan,
        status=sub.status.value,
        stripe_subscription_id=sub.stripe_subscription_id,
        current_period_end=(
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        cancel_at_period_end=sub.cancel_at_period_end,
    )


@router.post("/cancel", status_code=200)
@limiter.limit("5/minute")
def cancel_subscription(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cancela la suscripción al final del período de facturación actual.
    El usuario sigue en el plan hasta que venza.
    """
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()

    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenés una suscripción activa para cancelar.",
        )

    if sub.status == SubscriptionStatus.CANCELED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La suscripción ya fue cancelada.",
        )

    try:
        stripe.Subscription.modify(
            sub.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        sub.cancel_at_period_end = True
        db.commit()
        logger.info("Suscripción marcada para cancelar | user=%s sub=%s",
                    current_user.id, sub.stripe_subscription_id)
    except stripe.error.StripeError as exc:
        logger.error("Error cancelando suscripción | user=%s error=%s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al cancelar la suscripción en Stripe.",
        )

    return {
        "message": "Suscripción programada para cancelarse al final del período.",
        "cancel_at_period_end": True,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Webhook (sin autenticación JWT — usa firma HMAC de Stripe)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook", status_code=200, include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """
    Endpoint para recibir webhooks de Stripe.
    Registralo en el Dashboard de Stripe apuntando a:
      https://tu-dominio/api/v1/billing/webhook

    Eventos que maneja:
      - checkout.session.completed
      - customer.subscription.updated
      - customer.subscription.deleted
      - invoice.payment_failed
    """
    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header stripe-signature requerido.",
        )

    payload = await request.body()

    try:
        result = handle_stripe_webhook(payload, stripe_signature, db)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signature inválida.",
        )
    except Exception as exc:
        logger.error("Error en webhook Stripe: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error procesando el webhook.",
        )

    return result
