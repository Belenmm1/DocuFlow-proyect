"""
app/models/api_key.py

Bloque 6.2 — API Keys para usuarios Pro/Enterprise.

Tabla:
  api_keys — claves de autenticación alternativa al JWT
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id          = Column(String(36),  primary_key=True, index=True)

    # La clave que el usuario copia (solo se muestra UNA VEZ al crearla)
    # Se almacena el hash sha256, nunca el valor en claro.
    key_hash    = Column(String(64),  nullable=False, unique=True, index=True)

    # Prefijo visible (ej: "df_live_AbCdEf") para identificar la clave sin exponer el secreto
    key_prefix  = Column(String(16),  nullable=False)

    name        = Column(String(128), nullable=False)          # nombre descriptivo
    description = Column(Text,        nullable=True)

    user_id     = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner = relationship("User", back_populates="api_keys")

    is_active   = Column(Boolean, default=True,  nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    created_at  = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime, nullable=True)   # None = sin expiración
