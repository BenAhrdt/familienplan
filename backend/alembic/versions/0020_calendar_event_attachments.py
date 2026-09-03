"""add calendar event attachments

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "calendar_event_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("calendar_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calendar_event_attachments_event_id", "calendar_event_attachments", ["event_id"])


def downgrade():
    op.drop_index("ix_calendar_event_attachments_event_id", table_name="calendar_event_attachments")
    op.drop_table("calendar_event_attachments")
