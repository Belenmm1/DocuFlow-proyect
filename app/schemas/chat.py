"""
app/schemas/chat.py — Bloque 3.1

Schemas Pydantic para los endpoints de chat con documentos.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ─── Request ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Pregunta del usuario")
    conversation_id: Optional[str] = Field(
        default=None,
        description="UUID de la conversación existente. Si es None, se crea una nueva.",
    )


# ─── Response ─────────────────────────────────────────────────────────────────

class SourceChunk(BaseModel):
    """Fragmento del documento usado como contexto."""
    content: str
    page: Optional[int] = None

    class Config:
        from_attributes = True


class ChatMessageOut(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    sources: Optional[List[SourceChunk]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessageOut        # respuesta del asistente
    sources: List[SourceChunk]     # fragmentos del doc usados


class ConversationOut(BaseModel):
    id: str
    doc_id: int
    user_id: Optional[str]
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    class Config:
        from_attributes = True


class ConversationHistoryOut(BaseModel):
    conversation: ConversationOut
    messages: List[ChatMessageOut]
