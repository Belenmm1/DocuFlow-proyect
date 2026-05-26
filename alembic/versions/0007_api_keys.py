"""api_keys

Revision ID: 0007
Revises: 0006
Create Date: 2025-01-01 00:00:00

Bloque 6.2 — Crea la tabla `api_keys`.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id",           sa.String(36),  nullable=False),
        sa.Column("key_hash",     sa.String(64),  nullable=False),
        sa.Column("key_prefix",   sa.String(16),  nullable=False),
        sa.Column("name",         sa.String(128), nullable=False),
        sa.Column("description",  sa.Text(),      nullable=True),
        sa.Column("user_id",      sa.String(36),  nullable=False),
        sa.Column("is_active",    sa.Boolean(),   nullable=False, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(),  nullable=True),
        sa.Column("created_at",   sa.DateTime(),  nullable=True),
        sa.Column("expires_at",   sa.DateTime(),  nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_api_keys_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_user_id",  "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("ix_api_keys_is_active","api_keys", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_is_active", table_name="api_keys")
    op.drop_index("ix_api_keys_key_hash",  table_name="api_keys")
    op.drop_index("ix_api_keys_user_id",   table_name="api_keys")
    op.drop_table("api_keys")
