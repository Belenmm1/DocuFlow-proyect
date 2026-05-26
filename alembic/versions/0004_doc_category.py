"""doc_category

Revision ID: 0004
Revises: 0003
Create Date: 2024-01-03 00:00:00

Bloque 3.2 — Detección automática de tipo de documento.

Agrega dos columnas a la tabla `documents`:
  doc_category            → categoría detectada (contrato, factura, cv, etc.)
  doc_category_confidence → confianza de la clasificación (alta, media, baja)

Índice en doc_category para filtros por tipo de documento en listados.
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("doc_category", sa.String(32), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("doc_category_confidence", sa.String(8), nullable=True),
    )
    op.create_index(
        "ix_documents_doc_category",
        "documents",
        ["doc_category"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_doc_category", table_name="documents")
    op.drop_column("documents", "doc_category_confidence")
    op.drop_column("documents", "doc_category")
