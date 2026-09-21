"""Personenadressen und Verkehrspartner

Revision ID: 0027
Revises: 0026
"""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("address", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("traffic_partner_user_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.alter_column("users", "traffic_partner_user_ids", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "traffic_partner_user_ids")
    op.drop_column("users", "address")
