# app/api/v1/schemas/documents.py
"""
Schemas de documentos — actualizado en Bloque 2.3:
  - DocumentResponse agrega extracted_text_snippet para search highlighting
  - DocumentListItem: versión liviana para listas paginadas (sin texto completo)
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.database import DocumentStatus


class DocumentListItem(BaseModel):
    """
    Versión liviana del documento para respuestas de lista paginada.
    No incluye extracted_text completo (puede ser muy grande).
    Incluye un snippet del texto para mostrar contexto en búsquedas.
    """
    id: int
    filename: str
    file_type: str
    file_size: Optional[int]
    status: DocumentStatus
    task_id: Optional[str]
    summary: Optional[str]
    sentiment: Optional[str]
    keywords: Optional[list]
    page_count: Optional[int]
    # Snippet del texto extraído (máx 300 chars) para highlight en resultados de búsqueda
    extracted_text_snippet: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: Optional[int]
    status: DocumentStatus
    task_id: Optional[str]
    summary: Optional[str]
    key_entities: Optional[dict]
    sentiment: Optional[str]
    keywords: Optional[list]
    page_count: Optional[int]
    extracted_text: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DocumentStatusResponse(BaseModel):
    doc_id: int
    status: DocumentStatus
    task_id: Optional[str]
    task_info: Optional[dict]
    error_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
