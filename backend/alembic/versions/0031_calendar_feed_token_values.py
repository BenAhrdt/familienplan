"""Wieder abrufbare Kalenderfeed-Adressen

Revision ID: 0031
Revises: 0030
"""

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_feeds", sa.Column("token_value", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_feeds", "token_value")
