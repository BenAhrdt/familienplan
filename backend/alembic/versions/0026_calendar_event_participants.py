"""Add additional participants to calendar events."""

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("calendar_events", sa.Column("participant_user_ids", sa.JSON(), nullable=False, server_default="[]"))

def downgrade():
    op.drop_column("calendar_events", "participant_user_ids")
