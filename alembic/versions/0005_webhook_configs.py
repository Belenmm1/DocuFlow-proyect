"""webhook_configs

Revision ID: 0005
Revises: 0004_doc_category
Create Date: 2025-01-01 00:00:00

Bloque 5.1 — Crea la tabla `webhook_configs`.

Tabla:
  webhook_configs
    id          VARCHAR(36)  PK
    user_id     VARCHAR(36)  FK → users.id  ON DELETE CASCADE
    url         TEXT         NOT NULL
    events      JSON         NOT NULL   (lista de strings)
    secret      VARCHAR(128) NOT NULL
    is_active   BOOLEAN      NOT NULL   DEFAULT true
    created_at  TIMESTAMP    NOT NULL
    updated_at  TIMESTAMP    NOT NULL

Índices:
  ix_webhook_configs_user_id  — queries por usuario
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_configs",
        sa.Column("id",         sa.String(36),   nullable=False),
        sa.Column("user_id",    sa.String(36),   nullable=False),
        sa.Column("url",        sa.Text(),        nullable=False),
        sa.Column("events",     sa.JSON(),        nullable=False),
        sa.Column("secret",     sa.String(128),  nullable=False),
        sa.Column("is_active",  sa.Boolean(),    nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(),   nullable=False),
        sa.Column("updated_at", sa.DateTime(),   nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_webhook_configs_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_configs_user_id",
        "webhook_configs",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_configs_user_id", table_name="webhook_configs")
    op.drop_table("webhook_configs")
