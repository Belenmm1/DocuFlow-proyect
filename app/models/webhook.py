"""
app/models/webhook.py

Modelo SQLAlchemy para la configuración de webhooks de usuario.

Cada registro representa un endpoint externo al que DocuFlow enviará
una notificación HTTP cuando ocurra alguno de los eventos suscritos.

Campos:
  id          — UUID generado en Python (compatible SQLite + PostgreSQL)
  user_id     — FK al usuario propietario
  url         — endpoint destino (HTTPS recomendado en producción)
  events      — lista JSON de eventos suscritos, ej: ["done", "failed"]
  secret      — clave para firmar el payload con HMAC-SHA256
  is_active   — permite desactivar sin eliminar
  created_at  — timestamp de creación
  updated_at  — timestamp de última modificación

Eventos válidos (WebhookEvent):
  document.done    — el análisis IA terminó con éxito
  document.failed  — el procesamiento falló definitivamente
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum,
    ForeignKey, JSON, String, Text
)
from sqlalchemy.orm import relationship

from app.models.database import Base


class WebhookEvent(str, enum.Enum):
    DOCUMENT_DONE   = "document.done"
    DOCUMENT_FAILED = "document.failed"


class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    url        = Column(Text, nullable=False)
    events     = Column(JSON, nullable=False, default=list)   # ["document.done", ...]
    secret     = Column(String(128), nullable=False)           # generado automáticamente
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="webhooks")
