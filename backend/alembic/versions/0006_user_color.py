"""Add a calendar color for every person."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("color", sa.String(7), nullable=False, server_default="#3BA4E5"))


def downgrade() -> None:
    op.drop_column("users", "color")
