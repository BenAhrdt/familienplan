"""Entfernt Fahradressen und Verkehrspartner

Revision ID: 0028
Revises: 0027
"""

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "traffic_partner_user_ids")
    op.drop_column("users", "address")


def downgrade() -> None:
    op.add_column("users", sa.Column("address", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("traffic_partner_user_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.alter_column("users", "traffic_partner_user_ids", server_default=None)
