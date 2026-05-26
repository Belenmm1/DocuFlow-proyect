"""chat_tables

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-02 00:00:00

Bloque 3.1 — Chat con documentos (RAG).

Crea las tablas:
  chat_conversations  — conversaciones por (user, document)
  chat_messages       — mensajes de cada conversación

Índices:
  ix_chat_conv_doc_id         → listar conversaciones de un doc
  ix_chat_conv_user_id        → listar conversaciones de un user
  ix_chat_conv_doc_user       → compuesto (doc + user) — query más frecuente
  ix_chat_messages_conv_id    → listar mensajes de una conversación
  ix_chat_messages_created_at → ordenar cronológicamente
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── chat_conversations ───────────────────────────────────────────────────
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "doc_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_chat_conv_doc_id", "chat_conversations", ["doc_id"])
    op.create_index("ix_chat_conv_user_id", "chat_conversations", ["user_id"])
    op.create_index(
        "ix_chat_conv_doc_user",
        "chat_conversations",
        ["doc_id", "user_id"],
    )

    # ─── chat_messages ────────────────────────────────────────────────────────
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", name="messagerole"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", sa.Text(), nullable=True),    # JSON string
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
    op.create_index(
        "ix_chat_messages_conv_id",
        "chat_messages",
        ["conversation_id"],
    )
    op.create_index(
        "ix_chat_messages_created_at",
        "chat_messages",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_conv_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_chat_conv_doc_user", table_name="chat_conversations")
    op.drop_index("ix_chat_conv_user_id", table_name="chat_conversations")
    op.drop_index("ix_chat_conv_doc_id", table_name="chat_conversations")
    op.drop_table("chat_conversations")

    op.execute("DROP TYPE IF EXISTS messagerole")
