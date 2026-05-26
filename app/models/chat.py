"""
app/models/chat.py — Bloque 3.1

Modelos SQLAlchemy para el historial de chat con documentos (RAG).

Tablas:
  chat_conversations  — una conversación por (user, document)
  chat_messages       — mensajes individuales dentro de una conversación

Roles de mensaje:
  "user"      → pregunta del usuario
  "assistant" → respuesta generada por el LLM
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, Enum as SAEnum, Index,
)
from sqlalchemy.orm import relationship

from app.models.database import Base


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id = Column(String(36), primary_key=True)          # UUID generado en la app
    doc_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(255), nullable=True)          # primeras palabras del primer mensaje
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
        lazy="dynamic",
    )
    document = relationship("Document", backref="conversations")

    __table_args__ = (
        Index("ix_chat_conv_doc_user", "doc_id", "user_id"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(SAEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    # Fragmentos del documento usados como contexto (source chunks)
    sources = Column(Text, nullable=True)              # JSON string: [{page, snippet}, ...]
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    conversation = relationship("ChatConversation", back_populates="messages")
