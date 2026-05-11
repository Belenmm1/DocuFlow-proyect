# app/core/pagination.py
"""
Bloque 2.3 — Utilidades de paginación con cursor.

El cursor es un string base64 que codifica { "id": int, "dir": "next"|"prev" }.
Es opaco para el cliente: no debe interpretarlo ni construirlo manualmente.

Estrategia keyset pagination:
  - "siguiente página" → WHERE id < last_id (para desc) / WHERE id > last_id (para asc)
  - Es O(1) y no se degrada con tablas grandes, a diferencia del OFFSET clásico.

Para campos de orden distintos a `id`, se añade una condición compuesta:
  WHERE (order_field, id) < (last_order_value, last_id)   ← para desc
  WHERE (order_field, id) > (last_order_value, last_id)   ← para asc

Limitaciones conocidas:
  - El cursor se invalida si los registros se modifican entre páginas (aceptable para este caso).
  - Para full-text search con SQLite se usa LIKE; migrar a pg_trgm con PostgreSQL (Bloque 2.4).
"""
import base64
import json
import logging
from datetime import datetime
from typing import Any, Optional, Tuple

from sqlalchemy import asc, desc, or_, and_
from sqlalchemy.orm import Session

from app.models.database import Document, DocumentStatus

logger = logging.getLogger(__name__)

# Campos permitidos para ordenar (whitelist para evitar SQL injection)
ALLOWED_ORDER_FIELDS = {"id", "filename", "file_type", "status", "created_at", "file_size"}
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# ─── Cursor encoding/decoding ─────────────────────────────────────────────────

def encode_cursor(payload: dict) -> str:
    """Serializa el cursor a base64 URL-safe."""
    raw = json.dumps(payload, default=str)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> Optional[dict]:
    """Deserializa el cursor. Retorna None si es inválido."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(raw)
    except Exception:
        logger.warning(f"Cursor inválido recibido: {cursor!r}")
        return None


# ─── Query builder ────────────────────────────────────────────────────────────

def build_document_query(
    db: Session,
    *,
    status: Optional[str] = None,
    file_type: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    search: Optional[str] = None,
    order_by: str = "created_at",
    order_dir: str = "desc",
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: Optional[str] = None,
) -> Tuple[list, Optional[str], Optional[str], int]:
    """
    Ejecuta la query con filtros, ordenamiento y paginación por cursor.

    Retorna: (items, next_cursor, prev_cursor, total)
    """
    # Validar y normalizar parámetros
    limit = min(max(1, limit), MAX_PAGE_SIZE)
    if order_by not in ALLOWED_ORDER_FIELDS:
        order_by = "created_at"
    order_dir = "desc" if order_dir.lower() != "asc" else "asc"

    q = db.query(Document)

    # ── Filtros ───────────────────────────────────────────────────────────────
    if status:
        try:
            q = q.filter(Document.status == DocumentStatus(status))
        except ValueError:
            pass  # status inválido → ignorar filtro

    if file_type:
        q = q.filter(Document.file_type == file_type.lower())

    if fecha_desde:
        try:
            dt = datetime.fromisoformat(fecha_desde)
            q = q.filter(Document.created_at >= dt)
        except ValueError:
            pass

    if fecha_hasta:
        try:
            dt = datetime.fromisoformat(fecha_hasta)
            q = q.filter(Document.created_at <= dt)
        except ValueError:
            pass

    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Document.filename.ilike(term),
                Document.extracted_text.ilike(term),
                Document.summary.ilike(term),
            )
        )

    # ── Total (antes de aplicar cursor) ──────────────────────────────────────
    total = q.count()

    # ── Cursor: restricción keyset ────────────────────────────────────────────
    is_prev_page = False
    cursor_payload = None

    if cursor:
        cursor_payload = decode_cursor(cursor)
        if cursor_payload:
            cursor_id = cursor_payload.get("id")
            cursor_dir = cursor_payload.get("dir", "next")
            cursor_field_value = cursor_payload.get("field_value")
            is_prev_page = cursor_dir == "prev"

            order_col = getattr(Document, order_by)

            if order_by == "id":
                # Caso simple
                if (order_dir == "desc" and cursor_dir == "next") or (order_dir == "asc" and cursor_dir == "prev"):
                    q = q.filter(Document.id < cursor_id)
                else:
                    q = q.filter(Document.id > cursor_id)
            else:
                # Caso compuesto: (field, id)
                if cursor_field_value is not None:
                    try:
                        # Convertir el valor del cursor al tipo correcto
                        if order_by in ("created_at", "updated_at"):
                            parsed_value = datetime.fromisoformat(str(cursor_field_value))
                        elif order_by in ("file_size", "page_count"):
                            parsed_value = int(cursor_field_value) if cursor_field_value is not None else None
                        else:
                            parsed_value = str(cursor_field_value)

                        if (order_dir == "desc" and cursor_dir == "next") or (order_dir == "asc" and cursor_dir == "prev"):
                            q = q.filter(
                                or_(
                                    order_col < parsed_value,
                                    and_(order_col == parsed_value, Document.id < cursor_id),
                                )
                            )
                        else:
                            q = q.filter(
                                or_(
                                    order_col > parsed_value,
                                    and_(order_col == parsed_value, Document.id > cursor_id),
                                )
                            )
                    except (ValueError, TypeError):
                        pass  # cursor corrupto → ignorar restricción

    # ── Ordenamiento ──────────────────────────────────────────────────────────
    order_col = getattr(Document, order_by)
    direction = desc if order_dir == "desc" else asc

    # Para páginas previas invertimos el orden, luego revertimos el resultado
    if is_prev_page:
        opposite = asc if order_dir == "desc" else desc
        q = q.order_by(opposite(order_col), opposite(Document.id))
    else:
        q = q.order_by(direction(order_col), direction(Document.id))

    # Fetch limit + 1 para saber si hay página siguiente
    rows = q.limit(limit + 1).all()

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    if is_prev_page:
        rows = list(reversed(rows))

    # ── Generar cursores ──────────────────────────────────────────────────────
    next_cursor = None
    prev_cursor = None

    if rows:
        first = rows[0]
        last = rows[-1]

        first_field_val = getattr(first, order_by)
        last_field_val = getattr(last, order_by)

        # next_cursor apunta al último elemento de esta página
        if has_more:
            next_cursor = encode_cursor({
                "id": last.id,
                "dir": "next",
                "field_value": last_field_val,
            })

        # prev_cursor existe si llegamos aquí con un cursor (no es la primera página)
        if cursor_payload:
            prev_cursor = encode_cursor({
                "id": first.id,
                "dir": "prev",
                "field_value": first_field_val,
            })

    return rows, next_cursor, prev_cursor, total


# ─── Snippet builder para full-text search ───────────────────────────────────

def build_snippet(text: Optional[str], search_term: Optional[str], max_len: int = 300) -> Optional[str]:
    """
    Genera un snippet del texto extraído centrado alrededor del término buscado.
    Si no hay término de búsqueda, retorna los primeros max_len caracteres.
    """
    if not text:
        return None

    if not search_term or not search_term.strip():
        snippet = text[:max_len]
        return snippet + "…" if len(text) > max_len else snippet

    term = search_term.strip().lower()
    lower_text = text.lower()
    idx = lower_text.find(term)

    if idx == -1:
        snippet = text[:max_len]
        return snippet + "…" if len(text) > max_len else snippet

    # Centrar el snippet alrededor del match
    half = max_len // 2
    start = max(0, idx - half)
    end = min(len(text), idx + len(term) + half)

    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"

    return snippet
