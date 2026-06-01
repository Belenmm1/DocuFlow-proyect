"""mejoras_v2 — timezone, monthly_docs_count, doc_category en documentos

Revision ID: 0009_mejoras_v2
Revises: 2b3c4d5e6f7a
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_mejoras_v2'
down_revision = '2b3c4d5e6f7a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agregar monthly_docs_count al modelo User
    op.add_column('users',
        sa.Column('monthly_docs_count', sa.Integer(), nullable=False, server_default='0')
    )

    # Cambiar created_at / updated_at de documentos a timezone-aware
    # PostgreSQL: USING cast
    with op.batch_alter_table('documents') as batch_op:
        batch_op.alter_column(
            'created_at',
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(timezone=False),
            postgresql_using='created_at AT TIME ZONE \'UTC\'',
        )
        batch_op.alter_column(
            'updated_at',
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(timezone=False),
            postgresql_using='updated_at AT TIME ZONE \'UTC\'',
        )


def downgrade() -> None:
    with op.batch_alter_table('documents') as batch_op:
        batch_op.alter_column('created_at', type_=sa.DateTime(timezone=False))
        batch_op.alter_column('updated_at', type_=sa.DateTime(timezone=False))

    op.drop_column('users', 'monthly_docs_count')
