# app/api/v1/schemas/pagination.py
"""
Bloque 2.3 — Paginación y Búsqueda
Schemas para respuestas paginadas con cursor y filtros combinables.
"""
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    """
    Respuesta paginada con cursor opaco.

    - items: lista de resultados de esta página
    - next_cursor: string opaco para obtener la página siguiente (None si no hay más)
    - prev_cursor: string opaco para volver a la página anterior (None si es la primera)
    - total: total de items que coinciden con los filtros (sin paginar)
    - page_size: cantidad de items en esta respuesta
    """
    items: List[T]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    total: int
    page_size: int


class DocumentFilters(BaseModel):
    """
    Filtros combinables para la lista de documentos.
    Todos son opcionales; se aplican en AND.
    """
    status: Optional[str] = Field(
        default=None,
        description="Estado del documento: pending | processing | done | failed",
    )
    file_type: Optional[str] = Field(
        default=None,
        description="Tipo de archivo: pdf | docx | xlsx",
    )
    fecha_desde: Optional[str] = Field(
        default=None,
        description="Fecha de creación mínima en ISO 8601 (ej: 2024-01-01T00:00:00)",
    )
    fecha_hasta: Optional[str] = Field(
        default=None,
        description="Fecha de creación máxima en ISO 8601 (ej: 2024-12-31T23:59:59)",
    )
    search: Optional[str] = Field(
        default=None,
        description="Búsqueda full-text en filename y extracted_text",
    )
    order_by: str = Field(
        default="created_at",
        description="Campo por el que ordenar: id | filename | file_type | status | created_at | file_size",
    )
    order_dir: str = Field(
        default="desc",
        description="Dirección de orden: asc | desc",
    )
