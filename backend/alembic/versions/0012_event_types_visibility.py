"""event types, per-user permissions and audience selection

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

DEFAULT_TYPES = '["STAY", "BIRTHDAY", "GENERAL"]'


def upgrade():
    op.add_column("users", sa.Column("allowed_event_types", sa.JSON(), nullable=False, server_default=DEFAULT_TYPES))
    op.add_column("calendar_events", sa.Column("event_type", sa.String(30), nullable=False, server_default="GENERAL"))
    op.add_column("calendar_events", sa.Column("custom_type_label", sa.String(120)))
    op.add_column("calendar_events", sa.Column("visible_to_user_ids", sa.JSON()))
    op.create_index("ix_calendar_events_event_type", "calendar_events", ["event_type"])
    op.add_column("birthdays", sa.Column("visible_to_user_ids", sa.JSON()))


def downgrade():
    op.drop_column("birthdays", "visible_to_user_ids")
    op.drop_index("ix_calendar_events_event_type", table_name="calendar_events")
    op.drop_column("calendar_events", "visible_to_user_ids")
    op.drop_column("calendar_events", "custom_type_label")
    op.drop_column("calendar_events", "event_type")
    op.drop_column("users", "allowed_event_types")
