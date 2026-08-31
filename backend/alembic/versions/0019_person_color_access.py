"""add person color access

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("allowed_person_color_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("users", "allowed_person_color_ids")
