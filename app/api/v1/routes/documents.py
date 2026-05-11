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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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
from app.core.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_document_query,
    build_snippet,
)

router = APIRouter(prefix="/documents", tags=["documents"])
file_handler = FileHandler()


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
    """
    file_info = await file_handler.save(file)

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

    return doc


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

    db.delete(doc)
    db.commit()
