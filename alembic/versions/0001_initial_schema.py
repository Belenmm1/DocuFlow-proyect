"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00

Bloque 2.4 — Migración inicial para PostgreSQL.

Crea las tablas `users` y `documents` con todos los campos acumulados
hasta el Bloque 2.3 (inclusive), e índices recomendados para producción.

Índices incluidos:
  users:
    - ix_users_email (unique)

  documents:
    - ix_documents_user_id
    - ix_documents_status
    - ix_documents_file_type
    - ix_documents_created_at
    - ix_documents_status_created_at (compuesto)
    - ix_documents_user_id_created_at (compuesto)

Nota PostgreSQL full-text search:
  Una vez que tengas datos, podés agregar manualmente:
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE INDEX ix_documents_extracted_text_trgm
      ON documents USING GIN (extracted_text gin_trgm_ops);
  Esto acelera las búsquedas ILIKE del Bloque 2.3.
  Se hace fuera de Alembic porque requiere la extensión pg_trgm habilitada.
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── Tabla users ─────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column(
            "hashed_password",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "admin", name="userrole"),
            nullable=False,
            server_default="user",
        ),
        sa.Column(
            "plan",
            sa.Enum("free", "pro", "enterprise", name="userplan"),
            nullable=False,
            server_default="free",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ─── Tabla documents ─────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        # Bloque 2.1 — async processing
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "done", "failed", name="documentstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("task_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        # Análisis IA
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_entities", sa.JSON(), nullable=True),
        sa.Column("sentiment", sa.String(32), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
        ),
        # FK a users (Bloque 1.1)
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )

    # Índices simples
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_file_type", "documents", ["file_type"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])
    op.create_index("ix_documents_file_size", "documents", ["file_size"])
    op.create_index("ix_documents_filename", "documents", ["filename"])

    # Índices compuestos — queries frecuentes del Bloque 2.3
    op.create_index(
        "ix_documents_status_created_at",
        "documents",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_documents_user_id_created_at",
        "documents",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    # Índices compuestos
    op.drop_index("ix_documents_user_id_created_at", table_name="documents")
    op.drop_index("ix_documents_status_created_at", table_name="documents")

    # Índices simples
    op.drop_index("ix_documents_filename", table_name="documents")
    op.drop_index("ix_documents_file_size", table_name="documents")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_file_type", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_user_id", table_name="documents")

    op.drop_table("documents")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    # Eliminar tipos ENUM (solo necesario en PostgreSQL)
    op.execute("DROP TYPE IF EXISTS documentstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS userplan")
