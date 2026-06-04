"""bloque_2_3_indexes

Revision ID: 2b3c4d5e6f7a
Revises: 0008
Create Date: 2024-01-01 00:00:00

Bloque 2.3 — Paginación y Búsqueda:
  Agrega índices para acelerar filtros, ordenamiento y full-text search.

Índices agregados en `documents`:
  - ix_documents_file_type    → filtro por tipo de archivo
  - ix_documents_created_at   → ORDER BY y filtros de fecha
  - ix_documents_file_size    → ORDER BY file_size
  - ix_documents_filename     → búsqueda y ORDER BY filename
  - ix_documents_status_created (compuesto) → filtro status + orden fecha (query más común)

Nota SQLite:
  SQLite no soporta índices de texto completo (FTS) via Alembic directamente.
  El FTS con LIKE funciona pero es O(n). Al migrar a PostgreSQL (Bloque 2.4)
  se recomienda agregar un índice GIN con pg_trgm:
    CREATE INDEX ix_documents_extracted_text_trgm
    ON documents USING GIN (extracted_text gin_trgm_ops);
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "2b3c4d5e6f7a"
down_revision = "0008"   # ← apunta a la migración del Bloque 2.1/2.2
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: all indexes listed above were already created by 0001_initial_schema.py.
    # Attempting to recreate them crashes with "index already exists" and
    # prevents uvicorn from starting. The indexes remain in place; nothing to do.
    pass


def downgrade() -> None:
    # No-op: mirrors upgrade — we never created the indexes here, so we must
    # not drop them; they belong to 0001_initial_schema.py.
    pass