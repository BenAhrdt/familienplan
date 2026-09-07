"""Store child timetables separately from calendar events."""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("children", sa.Column("timetable", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("children", "timetable")
