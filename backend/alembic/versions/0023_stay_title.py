"""add optional stay title

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("stays", sa.Column("title", sa.String(300), nullable=True))


def downgrade():
    op.drop_column("stays", "title")
