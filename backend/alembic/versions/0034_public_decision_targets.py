"""Einzelne Einträge in Gruppenanfragen per E-Mail entscheiden

Revision ID: 0034
Revises: 0033
"""

from alembic import op
import sqlalchemy as sa


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("public_decision_tokens", sa.Column("target_items", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("public_decision_tokens", "target_items")
