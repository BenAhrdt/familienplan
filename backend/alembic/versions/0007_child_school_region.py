"""Store school address and federal-state code per child."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("children", sa.Column("school_address", sa.String(500), nullable=True))
    op.add_column("children", sa.Column("school_state_code", sa.String(2), nullable=True))
    op.execute("UPDATE children SET school_state_code = 'HE' WHERE lower(coalesce(school_city, '')) = 'wiesbaden'")


def downgrade() -> None:
    op.drop_column("children", "school_state_code")
    op.drop_column("children", "school_address")
