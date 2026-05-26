"""subscriptions_and_stripe_events

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-01 00:00:00

Bloque 6.1 — Crea las tablas:
  subscriptions   — suscripción activa de cada usuario (vínculo con Stripe)
  stripe_events   — log idempotente de webhooks de Stripe
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscriptions ─────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id",                      sa.String(36),  nullable=False),
        sa.Column("user_id",                 sa.String(36),  nullable=False),
        sa.Column("stripe_customer_id",      sa.String(64),  nullable=True),
        sa.Column("stripe_subscription_id",  sa.String(64),  nullable=True),
        sa.Column("stripe_price_id",         sa.String(64),  nullable=True),
        sa.Column("plan",                    sa.String(16),  nullable=False, server_default="free"),
        sa.Column(
            "status",
            sa.Enum(
                "active", "trialing", "past_due", "canceled", "incomplete",
                name="subscriptionstatus",
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("current_period_start",    sa.DateTime(),  nullable=True),
        sa.Column("current_period_end",      sa.DateTime(),  nullable=True),
        sa.Column("cancel_at_period_end",    sa.Boolean(),   nullable=False, server_default=sa.text("false")),
        sa.Column("created_at",              sa.DateTime(),  nullable=True),
        sa.Column("updated_at",              sa.DateTime(),  nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_subscriptions_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id",               name="uq_subscriptions_user_id"),
        sa.UniqueConstraint("stripe_subscription_id", name="uq_subscriptions_stripe_sub_id"),
    )
    op.create_index("ix_subscriptions_user_id",               "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_stripe_customer_id",    "subscriptions", ["stripe_customer_id"])
    op.create_index("ix_subscriptions_stripe_subscription_id","subscriptions", ["stripe_subscription_id"])
    op.create_index("ix_subscriptions_status",                "subscriptions", ["status"])

    # ── stripe_events ─────────────────────────────────────────────────────────
    op.create_table(
        "stripe_events",
        sa.Column("id",         sa.String(64),  nullable=False),   # event.id de Stripe
        sa.Column("event_type", sa.String(64),  nullable=False),
        sa.Column("processed",  sa.Boolean(),   nullable=False, server_default=sa.text("false")),
        sa.Column("error",      sa.Text(),      nullable=True),
        sa.Column("created_at", sa.DateTime(),  nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stripe_events_event_type", "stripe_events", ["event_type"])
    op.create_index("ix_stripe_events_created_at", "stripe_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_stripe_events_created_at",              table_name="stripe_events")
    op.drop_index("ix_stripe_events_event_type",              table_name="stripe_events")
    op.drop_table("stripe_events")

    op.drop_index("ix_subscriptions_status",                  table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_subscription_id",  table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_customer_id",      table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id",                 table_name="subscriptions")
    op.drop_table("subscriptions")

    # Eliminar el tipo enum en PostgreSQL
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
