"""
app/models/oauth_token.py

Bloque 5.3 — Modelo para almacenar tokens OAuth2 de integraciones externas.

Un usuario puede tener un token por proveedor (google, dropbox).
El access_token se renueva automáticamente usando el refresh_token.

IMPORTANTE: en producción encriptá access_token y refresh_token en reposo.
Una opción simple es usar cryptography.fernet con una clave derivada de SECRET_KEY.
Para este bloque guardamos en texto plano (suficiente para desarrollo).
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.database import Base


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    # Restricción única: un usuario solo puede tener un token activo por proveedor
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id       = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    provider      = Column(String(32), nullable=False)   # "google" | "dropbox"

    access_token  = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)          # None si el proveedor no lo entrega
    token_type    = Column(String(32), default="Bearer")
    scope         = Column(Text, nullable=True)

    # Cuándo expira el access_token (None = sin expiración conocida)
    expires_at    = Column(DateTime, nullable=True)

    # Información de la cuenta externa (para mostrar en UI)
    provider_email = Column(String(255), nullable=True)   # email de la cuenta conectada
    provider_name  = Column(String(255), nullable=True)   # nombre/display name

    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="oauth_tokens")

    def is_expired(self) -> bool:
        """True si el access_token ya expiró (con 60s de margen)."""
        if self.expires_at is None:
            return False
        from datetime import timezone, timedelta
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return now >= (self.expires_at - timedelta(seconds=60))

    def __repr__(self) -> str:
        return f"<OAuthToken user={self.user_id} provider={self.provider}>"
