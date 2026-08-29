"""Add recurrence, color and privacy to calendar events."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE calendar_events
          ADD COLUMN created_by_id INTEGER REFERENCES users(id),
          ADD COLUMN color VARCHAR(7),
          ADD COLUMN is_private BOOLEAN NOT NULL DEFAULT false,
          ADD COLUMN recurrence_group VARCHAR(36),
          ADD COLUMN recurrence_frequency VARCHAR(10),
          ADD COLUMN recurrence_interval INTEGER,
          ADD COLUMN recurrence_until TIMESTAMPTZ;
        CREATE INDEX ix_calendar_events_created_by_id ON calendar_events(created_by_id);
        CREATE INDEX ix_calendar_events_recurrence_group ON calendar_events(recurrence_group);
    """)


def downgrade():
    op.execute("""
        DROP INDEX IF EXISTS ix_calendar_events_recurrence_group;
        DROP INDEX IF EXISTS ix_calendar_events_created_by_id;
        ALTER TABLE calendar_events
          DROP COLUMN recurrence_until,
          DROP COLUMN recurrence_interval,
          DROP COLUMN recurrence_frequency,
          DROP COLUMN recurrence_group,
          DROP COLUMN is_private,
          DROP COLUMN color,
          DROP COLUMN created_by_id;
    """)
