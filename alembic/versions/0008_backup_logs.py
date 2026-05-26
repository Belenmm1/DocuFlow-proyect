"""0008 — backup_logs table (Bloque 7.4)

Revision ID: 0008
Revises: 0007_api_keys
Create Date: 2024-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backup_logs_id", "backup_logs", ["id"])
    op.create_index("ix_backup_logs_created_at", "backup_logs", ["created_at"])
    op.create_index("ix_backup_logs_status", "backup_logs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_backup_logs_status", table_name="backup_logs")
    op.drop_index("ix_backup_logs_created_at", table_name="backup_logs")
    op.drop_index("ix_backup_logs_id", table_name="backup_logs")
    op.drop_table("backup_logs")
