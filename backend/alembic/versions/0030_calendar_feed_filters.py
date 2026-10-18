"""Kategorien pro Kalenderfeed

Revision ID: 0030
Revises: 0029
"""

from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_feeds", sa.Column("event_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.alter_column("calendar_feeds", "event_types", server_default=None)


def downgrade() -> None:
    op.drop_column("calendar_feeds", "event_types")
