"""
app/api/v1/routes/chat.py — Bloque 3.1

Endpoints de chat con documentos (RAG).

Rutas:
  POST   /documents/{doc_id}/chat
         Envía un mensaje. Crea conversación nueva si no se pasa conversation_id.
         Retorna la respuesta del asistente + fuentes del documento usadas.

  GET    /documents/{doc_id}/chat
         Lista todas las conversaciones del usuario para este documento.

  GET    /documents/{doc_id}/chat/{conversation_id}
         Recupera el historial completo de una conversación.

  DELETE /documents/{doc_id}/chat/{conversation_id}
         Elimina una conversación y todos sus mensajes.
"""

import json
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.models.chat import ChatConversation, ChatMessage, MessageRole
from app.models.database import Document, DocumentStatus, get_db
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatMessageOut,
    ConversationHistoryOut,
    ConversationOut,
    SourceChunk,
)
from app.services.rag_service import rag_service
from app.utils.logger import get_logger

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_document_or_404(doc_id: int, db: Session) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return doc


def _get_conversation_or_404(
    conversation_id: str, doc_id: int, user_id: str | None, db: Session
) -> ChatConversation:
    conv = (
        db.query(ChatConversation)
        .filter(
            ChatConversation.id == conversation_id,
            ChatConversation.doc_id == doc_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")

    # Verificar que pertenece al usuario autenticado
    if user_id and conv.user_id and conv.user_id != user_id:
        raise HTTPException(status_code=403, detail="Sin permiso para esta conversación.")

    return conv


def _parse_sources(sources_json: str | None) -> List[SourceChunk]:
    if not sources_json:
        return []
    try:
        raw = json.loads(sources_json)
        return [SourceChunk(**s) for s in raw]
    except Exception:
        return []


def _message_to_out(msg: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        role=msg.role.value,
        content=msg.content,
        sources=_parse_sources(msg.sources),
        created_at=msg.created_at,
    )


def _conversation_to_out(conv: ChatConversation, db: Session) -> ConversationOut:
    count = conv.messages.count()
    return ConversationOut(
        id=conv.id,
        doc_id=conv.doc_id,
        user_id=conv.user_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=count,
    )


# ─── POST /documents/{doc_id}/chat ────────────────────────────────────────────

@router.post(
    "/documents/{doc_id}/chat",
    response_model=ChatResponse,
    status_code=200,
    summary="Enviar mensaje al documento (RAG)",
)
async def chat_with_document(
    doc_id: int,
    body: ChatRequest,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_user),  # descomentar con auth activa
):
    """
    Envía una pregunta y recibe una respuesta basada en el contenido del documento.

    - Si `conversation_id` es `null`, se crea una nueva conversación.
    - El historial previo de la conversación se pasa al LLM para contexto.
    - Se retornan los fragmentos del documento usados como fuente.

    **Requisito**: el documento debe estar en status `done` (análisis completo).
    """
    # 1. Validar documento
    doc = _get_document_or_404(doc_id, db)

    if doc.status != DocumentStatus.DONE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El documento aún no está procesado (status={doc.status.value}). "
                   "Esperá a que el análisis termine antes de chatear.",
        )

    if not doc.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ERROR,
            detail="El documento no tiene texto extraído.",
        )

    # user_id = current_user.id  # con auth activa
    user_id = None

    # 2. Obtener o crear conversación
    if body.conversation_id:
        conv = _get_conversation_or_404(body.conversation_id, doc_id, user_id, db)
    else:
        # Crear nueva conversación con título basado en la primera pregunta
        title = body.message[:60] + ("..." if len(body.message) > 60 else "")
        conv = ChatConversation(
            id=str(uuid.uuid4()),
            doc_id=doc_id,
            user_id=user_id,
            title=title,
        )
        db.add(conv)
        db.flush()   # obtener el id sin commit aún

    # 3. Construir historial de mensajes para pasar al LLM
    history_msgs = [
        {"role": msg.role.value, "content": msg.content}
        for msg in conv.messages.order_by(ChatMessage.created_at).all()
    ]

    # 4. Guardar mensaje del usuario
    user_msg = ChatMessage(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=body.message,
    )
    db.add(user_msg)
    db.flush()

    # 5. Llamar al servicio RAG
    try:
        result = await rag_service.chat(
            doc_id=doc_id,
            doc_text=doc.extracted_text,
            question=body.message,
            history=history_msgs,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error en RAG chat — doc_id={doc_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al generar la respuesta. Intentá nuevamente.",
        )

    # 6. Guardar respuesta del asistente
    sources_json = json.dumps(result["sources"], ensure_ascii=False)
    assistant_msg = ChatMessage(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=result["answer"],
        sources=sources_json,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    db.refresh(conv)

    logger.info(
        f"Chat completado — doc_id={doc_id} | "
        f"conv_id={conv.id} | "
        f"sources={len(result['sources'])}"
    )

    return ChatResponse(
        conversation_id=conv.id,
        message=_message_to_out(assistant_msg),
        sources=[SourceChunk(**s) for s in result["sources"]],
    )


# ─── GET /documents/{doc_id}/chat ─────────────────────────────────────────────

@router.get(
    "/documents/{doc_id}/chat",
    response_model=List[ConversationOut],
    summary="Listar conversaciones del documento",
)
def list_conversations(
    doc_id: int,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_user),
):
    """Lista todas las conversaciones del usuario para este documento."""
    _get_document_or_404(doc_id, db)

    convs = (
        db.query(ChatConversation)
        .filter(ChatConversation.doc_id == doc_id)
        .order_by(ChatConversation.updated_at.desc())
        .all()
    )
    return [_conversation_to_out(c, db) for c in convs]


# ─── GET /documents/{doc_id}/chat/{conversation_id} ───────────────────────────

@router.get(
    "/documents/{doc_id}/chat/{conversation_id}",
    response_model=ConversationHistoryOut,
    summary="Historial de una conversación",
)
def get_conversation_history(
    doc_id: int,
    conversation_id: str,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_user),
):
    """Retorna la conversación completa con todos sus mensajes en orden cronológico."""
    _get_document_or_404(doc_id, db)
    conv = _get_conversation_or_404(conversation_id, doc_id, None, db)

    messages = (
        conv.messages
        .order_by(ChatMessage.created_at)
        .all()
    )

    return ConversationHistoryOut(
        conversation=_conversation_to_out(conv, db),
        messages=[_message_to_out(m) for m in messages],
    )


# ─── DELETE /documents/{doc_id}/chat/{conversation_id} ────────────────────────

@router.delete(
    "/documents/{doc_id}/chat/{conversation_id}",
    status_code=204,
    summary="Eliminar conversación",
)
def delete_conversation(
    doc_id: int,
    conversation_id: str,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_user),
):
    """Elimina la conversación y todos sus mensajes."""
    _get_document_or_404(doc_id, db)
    conv = _get_conversation_or_404(conversation_id, doc_id, None, db)
    db.delete(conv)
    db.commit()
    logger.info(f"Conversación eliminada — conv_id={conversation_id}")
