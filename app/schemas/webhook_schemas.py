"""
app/schemas/webhook.py

Schemas Pydantic para la API de webhooks.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, HttpUrl, field_validator, model_validator
from app.models.webhook import WebhookEvent


# ── Request schemas ───────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    """Body para POST /webhooks — crea un nuevo webhook."""
    url: HttpUrl
    events: List[WebhookEvent]
    is_active: bool = True

    @field_validator("events")
    @classmethod
    def events_not_empty(cls, v: List[WebhookEvent]) -> List[WebhookEvent]:
        if not v:
            raise ValueError("Debés suscribirte a al menos un evento.")
        # Deduplicar preservando orden
        seen, result = set(), []
        for e in v:
            if e not in seen:
                seen.add(e)
                result.append(e)
        return result


class WebhookUpdate(BaseModel):
    """Body para PATCH /webhooks/{id} — actualización parcial."""
    url:       Optional[HttpUrl]            = None
    events:    Optional[List[WebhookEvent]] = None
    is_active: Optional[bool]              = None

    @field_validator("events")
    @classmethod
    def events_not_empty(cls, v: Optional[List[WebhookEvent]]):
        if v is not None and len(v) == 0:
            raise ValueError("La lista de eventos no puede quedar vacía.")
        return v


# ── Response schemas ──────────────────────────────────────────────────────────

class WebhookOut(BaseModel):
    """Representación pública de un WebhookConfig."""
    id:         str
    url:        str
    events:     List[str]
    is_active:  bool
    created_at: datetime
    updated_at: datetime
    # El secret NO se expone en la respuesta por seguridad.
    # Se muestra una sola vez al momento de la creación (WebhookCreated).

    model_config = {"from_attributes": True}


class WebhookCreated(WebhookOut):
    """
    Respuesta de creación — incluye el secret en texto plano.
    Esta es la ÚNICA vez que el secret se devuelve al cliente.
    El usuario debe guardarlo; DocuFlow no lo expone de nuevo.
    """
    secret: str


class WebhookList(BaseModel):
    total: int
    items: List[WebhookOut]
