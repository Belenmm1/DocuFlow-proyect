# app/api/v1/routes/documents.py
"""
Endpoints de ingesta, consulta y listado de documentos.

Bloque 2.2 — Caché: al eliminar un documento se invalida su caché de análisis
              y las métricas globales de stats.

Bloque 2.3 — Paginación y Búsqueda:
  - GET /documents          → lista paginada con cursor, filtros combinables y full-text search
  - GET /documents/search   → alias semántico dedicado a búsquedas
  - GET /documents/{id}     → documento completo (sin cambios)
  - GET /documents/{id}/status → estado (sin cambios)
  - DELETE /documents/{id}  → elimina e invalida caché (sin cambios)
"""
from typing import Optional

from app.utils.logger import get_logger
logger = get_logger(__name__)

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel as PydanticBase
from sqlalchemy.orm import Session
from celery.result import AsyncResult

from app.models.database import Document, DocumentStatus, get_db
from app.workers.celery_app import celery_app
from app.workers.tasks import process_document
from app.utils.file_handler import FileHandler
from app.api.v1.schemas.documents import (
    DocumentListItem,
    DocumentResponse,
    DocumentStatusResponse,
)
from app.api.v1.schemas.pagination import CursorPage, DocumentFilters
from app.core.cache import cache_invalidate_document
from app.services.rag_service import rag_service   # Bloque 3.1
from app.core.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_document_query,
    build_snippet,
)

router = APIRouter(prefix="/documents", tags=["documents"])
file_handler = FileHandler()


# ─── Schemas inline ───────────────────────────────────────────────────────────

class ChatRequest(PydanticBase):
    message: str
    history: list = []
    conversation_id: Optional[str] = None


# ─── Upload ───────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=DocumentResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_user),  # descomentar con Bloque 1.1
):
    """
    Sube un documento y lo encola para procesamiento asíncrono.
    Retorna 202 Accepted con status='pending' inmediatamente.

    Mejoras v2.0:
      - Deduplicación por (filename + tamaño): si ya existe un doc idéntico
        pendiente o procesando, retorna ese en lugar de crear un duplicado.
      - Plan FREE: máx 10 documentos/mes. 402 si se supera el límite.
    """
    file_info = await file_handler.save(file)

    # ── Plan FREE: verificar límite mensual ──────────────────────────────────
    # (Activar cuando current_user esté habilitado — Bloque 1.1)
    # if hasattr(current_user, 'plan') and current_user.plan == "free":
    #     if current_user.monthly_docs_count >= 10:
    #         raise HTTPException(
    #             status_code=402,
    #             detail="Límite mensual alcanzado. Actualizá tu plan para continuar procesando."
    #         )

    # ── Deduplicación: evitar duplicados por reintentos fallidos ─────────────
    existing = (
        db.query(Document)
        .filter(
            Document.filename  == file_info["filename"],
            Document.file_size == file_info["file_size"],
            Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING]),
        )
        .first()
    )
    if existing:
        logger.info(
            f"Documento duplicado detectado (id={existing.id}) — retornando existente"
        )
        return existing

    doc = Document(
        filename=file_info["filename"],
        file_path=file_info["file_path"],
        file_type=file_info["file_type"],
        file_size=file_info["file_size"],
        status=DocumentStatus.PENDING,
        # user_id=current_user.id,  # descomentar con Bloque 1.1
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    task = process_document.delay(doc.id)
    doc.task_id = task.id
    db.commit()
    db.refresh(doc)

    # ── Incrementar contador mensual ─────────────────────────────────────────
    # (Activar junto con current_user)
    # current_user.monthly_docs_count = (current_user.monthly_docs_count or 0) + 1
    # db.commit()

    return doc


# ─── Comparar documentos ──────────────────────────────────────────────────────

@router.post("/compare")
async def compare_documents(
    doc_id_1: int,
    doc_id_2: int,
    db: Session = Depends(get_db),
):
    """
    Compara dos documentos usando IA y retorna las diferencias estructuradas.
    Ambos documentos deben tener status='done'.
    """
    from app.core.llm_provider import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    doc1 = db.query(Document).filter(Document.id == doc_id_1).first()
    doc2 = db.query(Document).filter(Document.id == doc_id_2).first()

    if not doc1:
        raise HTTPException(status_code=404, detail=f"Documento {doc_id_1} no encontrado")
    if not doc2:
        raise HTTPException(status_code=404, detail=f"Documento {doc_id_2} no encontrado")

    if doc1.status != DocumentStatus.DONE:
        raise HTTPException(status_code=400, detail=f"Documento {doc_id_1} no está procesado (status: {doc1.status.value})")
    if doc2.status != DocumentStatus.DONE:
        raise HTTPException(status_code=400, detail=f"Documento {doc_id_2} no está procesado (status: {doc2.status.value})")

    if not doc1.extracted_text or not doc2.extracted_text:
        raise HTTPException(status_code=400, detail="Ambos documentos necesitan texto extraído")

    # Limitar texto para no exceder contexto (primeros 4000 chars c/u)
    text1 = doc1.extracted_text[:4000]
    text2 = doc2.extracted_text[:4000]

    COMPARE_SYSTEM = """Sos un analista experto en comparación de documentos.
Comparás dos versiones de un documento y respondés SOLO con JSON (sin markdown):
{
  "cambios_agregados": ["texto nuevo en v2 que no estaba en v1"],
  "cambios_eliminados": ["texto en v1 que no está en v2"],
  "cambios_modificados": [{"original": "...", "nuevo": "..."}],
  "resumen_cambios": "descripción en 2-3 oraciones de qué cambió",
  "impacto": "alto | medio | bajo",
  "recomendacion": "qué revisar con atención"
}"""

    user_msg = f"""Documento 1 ({doc1.filename}):
{text1}

---

Documento 2 ({doc2.filename}):
{text2}

Compará ambos documentos e identificá las diferencias."""

    try:
        llm = get_llm(temperature=0.1, max_tokens=2000)
        response = await llm.ainvoke([
            SystemMessage(content=COMPARE_SYSTEM),
            HumanMessage(content=user_msg),
        ])

        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        import json as _json
        result = _json.loads(raw)

        return {
            "doc_1": {"id": doc1.id, "filename": doc1.filename},
            "doc_2": {"id": doc2.id, "filename": doc2.filename},
            "comparison": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en comparación: {str(e)}")


# ─── Lista paginada con filtros (2.3) ─────────────────────────────────────────

@router.get("", response_model=CursorPage[DocumentListItem])
def list_documents(
    # Paginación
    cursor: Optional[str] = Query(default=None, description="Cursor opaco de la página anterior"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items por página"),
    # Filtros
    status: Optional[str] = Query(default=None, description="pending | processing | done | failed"),
    file_type: Optional[str] = Query(default=None, description="pdf | docx | xlsx"),
    fecha_desde: Optional[str] = Query(default=None, description="ISO 8601: 2024-01-01T00:00:00"),
    fecha_hasta: Optional[str] = Query(default=None, description="ISO 8601: 2024-12-31T23:59:59"),
    # Búsqueda full-text
    search: Optional[str] = Query(default=None, description="Busca en filename, texto extraído y summary"),
    # Ordenamiento
    order_by: str = Query(default="created_at", description="id | filename | file_type | status | created_at | file_size"),
    order_dir: str = Query(default="desc", description="asc | desc"),
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_user),  # Bloque 1.1
):
    """
    Lista documentos con paginación por cursor, filtros combinables y búsqueda full-text.

    ### Cómo paginar
    1. Primera llamada: sin `cursor`, obtés `next_cursor` en la respuesta.
    2. Siguiente página: pasás `cursor=<next_cursor>`.
    3. Página anterior: pasás `cursor=<prev_cursor>`.
    4. Si `next_cursor` es `null`, llegaste al final.

    ### Filtros combinables
    Podés combinar todos los filtros. Se aplican en AND.

    ### Búsqueda full-text
    El parámetro `search` busca en `filename`, `extracted_text` y `summary`.
    La respuesta incluye `extracted_text_snippet` con el contexto alrededor del match.

    > **Nota SQLite**: usa LIKE (case-insensitive). Al migrar a PostgreSQL (Bloque 2.4)
    > se puede activar `pg_trgm` para búsqueda trigrama más precisa.
    """
    rows, next_cursor, prev_cursor, total = build_document_query(
        db,
        status=status,
        file_type=file_type,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        search=search,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        cursor=cursor,
    )

    # Construir items con snippet de búsqueda
    items = []
    for doc in rows:
        snippet = build_snippet(doc.extracted_text, search)
        item = DocumentListItem(
            id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            task_id=doc.task_id,
            summary=doc.summary,
            sentiment=doc.sentiment,
            keywords=doc.keywords,
            page_count=doc.page_count,
            extracted_text_snippet=snippet,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        items.append(item)

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        total=total,
        page_size=len(items),
    )


@router.get("/search", response_model=CursorPage[DocumentListItem])
def search_documents(
    q: str = Query(..., min_length=2, description="Término de búsqueda (mínimo 2 caracteres)"),
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: Optional[str] = Query(default=None),
    file_type: Optional[str] = Query(default=None),
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc"),
    db: Session = Depends(get_db),
):
    """
    Alias semántico para búsqueda full-text.
    Equivale a `GET /documents?search=<q>` con el parámetro renombrado a `q`.

    Útil para integrar con barras de búsqueda donde el parámetro convencional es `q`.
    """
    rows, next_cursor, prev_cursor, total = build_document_query(
        db,
        search=q,
        status=status,
        file_type=file_type,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        cursor=cursor,
    )

    items = [
        DocumentListItem(
            id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            task_id=doc.task_id,
            summary=doc.summary,
            sentiment=doc.sentiment,
            keywords=doc.keywords,
            page_count=doc.page_count,
            extracted_text_snippet=build_snippet(doc.extracted_text, q),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc in rows
    ]

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        total=total,
        page_size=len(items),
    )


# ─── Detalle ──────────────────────────────────────────────────────────────────

@router.get("/{doc_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    doc_id: int,
    db: Session = Depends(get_db),
):
    """
    Consulta el estado de procesamiento de un documento.
    Usar para polling mientras status sea 'pending' o 'processing'.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    task_info = None
    if doc.task_id and doc.status == DocumentStatus.PROCESSING:
        task = AsyncResult(doc.task_id, app=celery_app)
        task_info = {
            "celery_state": task.state,
            "retries": task.info.get("retries") if isinstance(task.info, dict) else None,
        }

    return DocumentStatusResponse(
        doc_id=doc.id,
        status=doc.status,
        task_id=doc.task_id,
        task_info=task_info,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
):
    """Obtiene un documento completo con su análisis (solo disponible cuando status='done')."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


# ─── Eliminar ─────────────────────────────────────────────────────────────────

@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
):
    """
    Elimina un documento. Si tiene tarea activa, la revoca.
    Bloque 2.2 — invalida el caché de análisis IA y de stats globales.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.task_id and doc.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
        celery_app.control.revoke(doc.task_id, terminate=True)

    await cache_invalidate_document(doc_id)
    rag_service.invalidate_index(doc_id)           # Bloque 3.1 — elimina índice FAISS

    db.delete(doc)
    db.commit()


# ─── Reprocesar ───────────────────────────────────────────────────────────────

@router.post("/{doc_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    doc_id: int,
    db: Session = Depends(get_db),
):
    """
    Resetea el estado de un documento fallido y lo reencola para reprocesar.
    Evita crear duplicados: reutiliza el mismo registro.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in (DocumentStatus.FAILED, DocumentStatus.DONE):
        raise HTTPException(
            status_code=400,
            detail=f"Solo se pueden reprocesar documentos en estado 'failed' o 'done'. Estado actual: {doc.status.value}"
        )

    # Resetear estado
    doc.status = DocumentStatus.PENDING
    doc.error_message = None
    doc.summary = None
    doc.key_entities = None
    doc.sentiment = None
    doc.keywords = None
    doc.doc_category = None
    doc.doc_category_confidence = None
    db.commit()

    # Encolar nueva tarea
    task = process_document.delay(doc.id)
    doc.task_id = task.id
    db.commit()
    db.refresh(doc)

    return doc


# ─── SSE: stream de estado ────────────────────────────────────────────────────

@router.get("/{doc_id}/status/stream")
async def stream_document_status(
    doc_id: int,
    db: Session = Depends(get_db),
):
    """
    Server-Sent Events: emite el estado del documento cada 3 segundos
    hasta que el procesamiento termine (done o failed).
    El frontend puede reemplazar el polling de setTimeout con esta conexión.
    """
    import asyncio
    import json as _json
    from fastapi.responses import StreamingResponse

    async def event_generator():
        while True:
            # Re-consultar en cada iteración para obtener el estado fresco
            fresh_doc = db.query(Document).filter(Document.id == doc_id).first()
            if not fresh_doc:
                yield f"data: {_json.dumps({'error': 'not_found'})}\n\n"
                break

            payload = _json.dumps({
                "status":        fresh_doc.status.value,
                "doc_id":        fresh_doc.id,
                "error_message": fresh_doc.error_message,
            })
            yield f"data: {payload}\n\n"

            if fresh_doc.status in (DocumentStatus.DONE, DocumentStatus.FAILED):
                break

            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",    # Nginx: disable buffering
            "Access-Control-Allow-Origin": "*",
        },
    )



# ─── Chat RAG ─────────────────────────────────────────────────────────────────

@router.post("/{doc_id}/chat")
async def chat_with_document(
    doc_id: int,
    body: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Chat RAG con un documento procesado.
    Requiere status='done' y extracted_text disponible.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if doc.status != DocumentStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"El documento debe estar procesado (status actual: {doc.status.value})"
        )
    if not doc.extracted_text:
        raise HTTPException(
            status_code=400,
            detail="El documento no tiene texto extraído disponible para chat"
        )

    result = await rag_service.chat(
        doc_id=doc.id,
        doc_text=doc.extracted_text,
        question=body.message,
        history=body.history,
    )

    return {
        "response": result["answer"],   # alias para frontend
        "answer":   result["answer"],   # compatibilidad
        "sources":  result.get("sources", []),
        "doc_id":   doc_id,
    }
