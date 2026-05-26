"""pg_trgm_full_text_search

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-01 01:00:00

Bloque 2.4 — Índice GIN pg_trgm para full-text search en PostgreSQL.

Esta migración:
  1. Activa la extensión pg_trgm (si no está activa).
  2. Crea índices GIN trigrama en extracted_text, summary y filename.

Esto acelera las búsquedas ILIKE usadas en el Bloque 2.3 de O(n) a O(log n).

NOTA: Esta migración falla en SQLite (se ignora con try/except).
      Si tu DATABASE_URL es SQLite, esta migración es un no-op seguro.
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Detectar si es PostgreSQL en tiempo de migración
def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite: no-op seguro
        return

    # Activar extensión pg_trgm
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Índice GIN en extracted_text (texto extraído del documento)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_extracted_text_trgm
        ON documents USING GIN (extracted_text gin_trgm_ops)
        """
    )

    # Índice GIN en summary (resumen IA)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_summary_trgm
        ON documents USING GIN (summary gin_trgm_ops)
        """
    )

    # Índice GIN en filename (búsqueda por nombre de archivo)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_filename_trgm
        ON documents USING GIN (filename gin_trgm_ops)
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute("DROP INDEX IF EXISTS ix_documents_filename_trgm")
    op.execute("DROP INDEX IF EXISTS ix_documents_summary_trgm")
    op.execute("DROP INDEX IF EXISTS ix_documents_extracted_text_trgm")
    # No dropeamos pg_trgm porque puede usarla otra parte del sistema
