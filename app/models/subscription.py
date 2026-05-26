"""
app/models/subscription.py

Bloque 6.1 — Planes y Billing con Stripe.

Tablas:
  subscriptions   — suscripción activa de cada usuario
  stripe_events   — log idempotente de eventos de webhook de Stripe
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum,
    ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class SubscriptionStatus(str, enum.Enum):
    ACTIVE    = "active"
    TRIALING  = "trialing"
    PAST_DUE  = "past_due"
    CANCELED  = "canceled"
    INCOMPLETE = "incomplete"


# ─────────────────────────────────────────────────────────────────────────────
# Subscription
# ─────────────────────────────────────────────────────────────────────────────

class Subscription(Base):
    """
    Una fila por usuario.  Se crea cuando el usuario suscribe a un plan pago
    y se actualiza vía webhooks de Stripe.  Los usuarios Free no tienen fila
    (o tienen status=canceled).
    """
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, index=True)

    # Relación con User
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # 1 suscripción activa por usuario
        index=True,
    )
    owner = relationship("User", back_populates="subscription")

    # IDs de Stripe
    stripe_customer_id    = Column(String(64), nullable=True, index=True)
    stripe_subscription_id = Column(String(64), nullable=True, unique=True, index=True)
    stripe_price_id       = Column(String(64), nullable=True)

    # Plan efectivo (sincronizado desde Stripe)
    plan   = Column(String(16), nullable=False, default="free")   # free | pro | enterprise
    status = Column(
        SAEnum(SubscriptionStatus),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
        index=True,
    )

    # Fechas del período de facturación
    current_period_start = Column(DateTime, nullable=True)
    current_period_end   = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# StripeEvent  (idempotency log)
# ─────────────────────────────────────────────────────────────────────────────

class StripeEvent(Base):
    """
    Registro de cada evento recibido del webhook de Stripe.
    Permite detectar duplicados (Stripe puede re-enviar el mismo evento).
    """
    __tablename__ = "stripe_events"

    id         = Column(String(64), primary_key=True)   # = event.id de Stripe
    event_type = Column(String(64), nullable=False, index=True)
    processed  = Column(Boolean, default=False, nullable=False)
    error      = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
