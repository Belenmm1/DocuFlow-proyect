"""bloque_2_1_async_processing

Revision ID: 2a1b3c4d5e6f
Revises: (revision anterior)
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "2a1b3c4d5e6f"
down_revision = None  # Reemplazar con el ID de la última migración
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Crear el tipo enum para PostgreSQL
    # (SQLite lo ignora, usa VARCHAR directamente)
    document_status = sa.Enum(
        "pending", "processing", "done", "failed",
        name="documentstatus"
    )

    # Agregar columnas nuevas a la tabla documents
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(
            sa.Column("task_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("error_message", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("page_count", sa.Integer(), nullable=True)
        )
        # Reemplazar campo status string por enum
        # (SQLite: ALTER + recreate; Postgres: USING cast)
        batch_op.alter_column(
            "status",
            existing_type=sa.String(),
            type_=document_status,
            existing_nullable=True,
            nullable=False,
            server_default="pending",
            postgresql_using="status::documentstatus",
        )

    # Índice en task_id para búsquedas rápidas
    op.create_index("ix_documents_task_id", "documents", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_task_id", table_name="documents")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("page_count")
        batch_op.drop_column("error_message")
        batch_op.drop_column("task_id")
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum("pending", "processing", "done", "failed", name="documentstatus"),
            type_=sa.String(),
            existing_nullable=False,
        )
