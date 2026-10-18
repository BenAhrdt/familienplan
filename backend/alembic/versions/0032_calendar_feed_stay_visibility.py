"""Betreuungsfilter pro Kalenderfeed

Revision ID: 0032
Revises: 0031
"""

from alembic import op
import sqlalchemy as sa


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_feeds", sa.Column("stay_visibility", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_feeds", "stay_visibility")
