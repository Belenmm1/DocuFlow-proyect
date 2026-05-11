"""bloque_2_3_indexes

Revision ID: 2b3c4d5e6f7a
Revises: 2a1b3c4d5e6f
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
down_revision = "2a1b3c4d5e6f"   # ← apunta a la migración del Bloque 2.1/2.2
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Índice en file_type para filtro por tipo
    op.create_index(
        "ix_documents_file_type",
        "documents",
        ["file_type"],
        unique=False,
    )

    # Índice en created_at para ORDER BY y filtros de rango de fecha
    op.create_index(
        "ix_documents_created_at",
        "documents",
        ["created_at"],
        unique=False,
    )

    # Índice en file_size para ORDER BY file_size
    op.create_index(
        "ix_documents_file_size",
        "documents",
        ["file_size"],
        unique=False,
    )

    # Índice en filename para ORDER BY y búsquedas por nombre
    op.create_index(
        "ix_documents_filename",
        "documents",
        ["filename"],
        unique=False,
    )

    # Índice compuesto (status, created_at) — query más frecuente:
    # listar documentos done ordenados por fecha
    op.create_index(
        "ix_documents_status_created_at",
        "documents",
        ["status", "created_at"],
        unique=False,
    )

    # Índice compuesto (user_id, created_at) — para cuando se active Bloque 1.1
    # Solo crea si la columna ya existe (puede fallar en SQLite sin el bloque auth)
    try:
        op.create_index(
            "ix_documents_user_id_created_at",
            "documents",
            ["user_id", "created_at"],
            unique=False,
        )
    except Exception:
        pass  # La columna user_id puede no existir aún


def downgrade() -> None:
    try:
        op.drop_index("ix_documents_user_id_created_at", table_name="documents")
    except Exception:
        pass

    op.drop_index("ix_documents_status_created_at", table_name="documents")
    op.drop_index("ix_documents_filename", table_name="documents")
    op.drop_index("ix_documents_file_size", table_name="documents")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_file_type", table_name="documents")
