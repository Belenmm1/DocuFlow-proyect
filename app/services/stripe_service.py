"""
app/services/stripe_service.py

Bloque 6.1 — Integración Stripe.

Responsabilidades:
  - Crear/obtener customer en Stripe
  - Crear sesión de Checkout para suscribirse a un plan
  - Crear sesión del Customer Portal para gestionar/cancelar
  - Procesar webhooks de Stripe (idempotente)
  - Sincronizar estado de suscripción con la BD local
"""

import uuid
import stripe
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.subscription import Subscription, SubscriptionStatus, StripeEvent
from app.models.user import User, UserPlan
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Configuración de Stripe ────────────────────────────────────────────────
stripe.api_key = settings.STRIPE_SECRET_KEY


# ─────────────────────────────────────────────────────────────────────────────
# Price IDs por plan (se configuran en .env)
# ─────────────────────────────────────────────────────────────────────────────

PLAN_PRICE_IDS: dict[str, str] = {
    "pro":        settings.STRIPE_PRICE_PRO,
    "enterprise": settings.STRIPE_PRICE_ENTERPRISE,
}

PRICE_TO_PLAN: dict[str, str] = {
    v: k for k, v in PLAN_PRICE_IDS.items() if v
}


# ─────────────────────────────────────────────────────────────────────────────
# Customer
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_customer(user: User, db: Session) -> str:
    """
    Devuelve el stripe_customer_id del usuario.
    Si no existe, lo crea en Stripe y lo persiste.
    """
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()

    if sub and sub.stripe_customer_id:
        return sub.stripe_customer_id

    # Crear customer en Stripe
    customer = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": user.id},
    )
    logger.info("Stripe customer creado | user_id=%s customer=%s", user.id, customer.id)

    if sub is None:
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id=user.id,
            plan="free",
            status=SubscriptionStatus.ACTIVE,
        )
        db.add(sub)

    sub.stripe_customer_id = customer.id
    db.commit()
    return customer.id


# ─────────────────────────────────────────────────────────────────────────────
# Checkout Session
# ─────────────────────────────────────────────────────────────────────────────

def create_checkout_session(user: User, plan: str, db: Session) -> str:
    """
    Crea una Stripe Checkout Session y devuelve la URL de redirección.
    `plan` debe ser "pro" o "enterprise".
    """
    price_id = PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(f"Plan desconocido o sin price_id configurado: {plan!r}")

    customer_id = get_or_create_customer(user, db)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.APP_URL}/billing/cancel",
        metadata={"user_id": user.id, "plan": plan},
        subscription_data={
            "metadata": {"user_id": user.id, "plan": plan},
        },
        allow_promotion_codes=True,
    )
    logger.info("Checkout session creada | user=%s plan=%s session=%s", user.id, plan, session.id)
    return session.url


# ─────────────────────────────────────────────────────────────────────────────
# Customer Portal
# ─────────────────────────────────────────────────────────────────────────────

def create_portal_session(user: User, db: Session) -> str:
    """
    Crea una sesión del Customer Portal de Stripe para que el usuario
    gestione o cancele su suscripción.
    """
    customer_id = get_or_create_customer(user, db)

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.APP_URL}/billing",
    )
    logger.info("Portal session creada | user=%s", user.id)
    return session.url


# ─────────────────────────────────────────────────────────────────────────────
# Webhook handler
# ─────────────────────────────────────────────────────────────────────────────

def handle_stripe_webhook(payload: bytes, sig_header: str, db: Session) -> dict:
    """
    Verifica la firma del webhook, previene duplicados y despacha el evento.
    Retorna {"processed": True/False, "event": event_type}.
    """
    # 1. Verificar firma
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError as exc:
        logger.warning("Firma de webhook inválida: %s", exc)
        raise ValueError("Invalid Stripe signature") from exc

    event_id   = event["id"]
    event_type = event["type"]

    # 2. Idempotencia: ignorar si ya fue procesado
    existing = db.query(StripeEvent).filter(StripeEvent.id == event_id).first()
    if existing and existing.processed:
        logger.info("Evento Stripe duplicado ignorado | id=%s type=%s", event_id, event_type)
        return {"processed": False, "event": event_type}

    # Registrar el evento (o actualizar si falló antes)
    if not existing:
        db.add(StripeEvent(id=event_id, event_type=event_type))
        db.commit()

    # 3. Despachar por tipo
    try:
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(event["data"]["object"], db)

        elif event_type in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            _handle_subscription_change(event["data"]["object"], db)

        elif event_type == "invoice.payment_failed":
            _handle_payment_failed(event["data"]["object"], db)

        # Marcar como procesado
        db.query(StripeEvent).filter(StripeEvent.id == event_id).update(
            {"processed": True, "error": None}
        )
        db.commit()
        logger.info("Evento Stripe procesado | id=%s type=%s", event_id, event_type)

    except Exception as exc:
        db.query(StripeEvent).filter(StripeEvent.id == event_id).update(
            {"processed": False, "error": str(exc)[:500]}
        )
        db.commit()
        logger.error("Error procesando evento Stripe | id=%s type=%s error=%s",
                     event_id, event_type, exc)
        raise

    return {"processed": True, "event": event_type}


# ─────────────────────────────────────────────────────────────────────────────
# Handlers internos
# ─────────────────────────────────────────────────────────────────────────────

def _handle_checkout_completed(session_obj: dict, db: Session) -> None:
    """Checkout exitoso → activar plan en la BD."""
    user_id = session_obj.get("metadata", {}).get("user_id")
    plan    = session_obj.get("metadata", {}).get("plan", "pro")
    stripe_sub_id = session_obj.get("subscription")

    if not user_id:
        logger.warning("checkout.session.completed sin user_id en metadata")
        return

    # Obtener detalles de la suscripción de Stripe
    stripe_sub = stripe.Subscription.retrieve(stripe_sub_id) if stripe_sub_id else None

    _upsert_subscription(
        db=db,
        user_id=user_id,
        plan=plan,
        stripe_sub=stripe_sub,
        new_status=SubscriptionStatus.ACTIVE,
    )
    # Actualizar plan en User
    _update_user_plan(db, user_id, plan)


def _handle_subscription_change(stripe_sub: dict, db: Session) -> None:
    """Actualización o cancelación de suscripción."""
    customer_id = stripe_sub.get("customer")
    sub_status  = stripe_sub.get("status")  # active | past_due | canceled | ...

    # Buscar user por customer_id
    local_sub = (
        db.query(Subscription)
        .filter(Subscription.stripe_customer_id == customer_id)
        .first()
    )
    if not local_sub:
        logger.warning("Suscripción no encontrada para customer=%s", customer_id)
        return

    # Determinar plan desde price_id
    items    = stripe_sub.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else None
    plan     = PRICE_TO_PLAN.get(price_id, "free")

    # Si cancela → downgrade a free
    if sub_status == "canceled":
        plan = "free"

    status_map = {
        "active":     SubscriptionStatus.ACTIVE,
        "trialing":   SubscriptionStatus.TRIALING,
        "past_due":   SubscriptionStatus.PAST_DUE,
        "canceled":   SubscriptionStatus.CANCELED,
        "incomplete": SubscriptionStatus.INCOMPLETE,
    }
    new_status = status_map.get(sub_status, SubscriptionStatus.PAST_DUE)

    _upsert_subscription(
        db=db,
        user_id=local_sub.user_id,
        plan=plan,
        stripe_sub=stripe_sub,
        new_status=new_status,
    )
    _update_user_plan(db, local_sub.user_id, plan)


def _handle_payment_failed(invoice: dict, db: Session) -> None:
    """Pago fallido → marcar suscripción como past_due."""
    customer_id = invoice.get("customer")
    local_sub = (
        db.query(Subscription)
        .filter(Subscription.stripe_customer_id == customer_id)
        .first()
    )
    if local_sub:
        local_sub.status = SubscriptionStatus.PAST_DUE
        db.commit()
        logger.info("Suscripción marcada past_due | user=%s", local_sub.user_id)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_subscription(
    db: Session,
    user_id: str,
    plan: str,
    stripe_sub: Optional[dict],
    new_status: SubscriptionStatus,
) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()

    if sub is None:
        sub = Subscription(id=str(uuid.uuid4()), user_id=user_id)
        db.add(sub)

    sub.plan   = plan
    sub.status = new_status

    if stripe_sub:
        sub.stripe_subscription_id = stripe_sub.get("id")
        sub.stripe_customer_id     = stripe_sub.get("customer")
        sub.stripe_price_id        = (
            stripe_sub.get("items", {}).get("data", [{}])[0]
            .get("price", {}).get("id")
        )
        # Convertir timestamps Unix → datetime
        pstart = stripe_sub.get("current_period_start")
        pend   = stripe_sub.get("current_period_end")
        if pstart:
            sub.current_period_start = datetime.fromtimestamp(pstart, tz=timezone.utc)
        if pend:
            sub.current_period_end = datetime.fromtimestamp(pend, tz=timezone.utc)
        sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)

    db.commit()
    db.refresh(sub)
    return sub


def _update_user_plan(db: Session, user_id: str, plan: str) -> None:
    from app.models.user import User, UserPlan
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        try:
            user.plan = UserPlan(plan)
        except ValueError:
            user.plan = UserPlan.FREE
        db.commit()
        logger.info("Plan de usuario actualizado | user=%s plan=%s", user_id, plan)
