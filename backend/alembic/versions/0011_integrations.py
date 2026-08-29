"""integration webhooks and durable outbox

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("webhook_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("secret", sa.String(256), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table("outbox_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("recipient_key", sa.String(320), nullable=False),
        sa.Column("event_key", sa.String(200), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel", "recipient_key", "event_key", name="uq_outbox_recipient_event"),
    )
    op.create_index("ix_outbox_due", "outbox_messages", ["delivered_at", "available_at"])


def downgrade():
    op.drop_table("outbox_messages")
    op.drop_table("webhook_endpoints")
