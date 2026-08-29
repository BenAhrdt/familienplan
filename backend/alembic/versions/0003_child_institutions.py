"""Store child institution metadata and remove unused prototype sources."""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE children ADD COLUMN school_city VARCHAR(160);
        ALTER TABLE children ADD COLUMN school_url VARCHAR(1000);
        ALTER TABLE children ADD COLUMN school_calendar_url VARCHAR(1000);
        ALTER TABLE children ADD COLUMN care_city VARCHAR(160);
        ALTER TABLE children ADD COLUMN care_url VARCHAR(1000);
        ALTER TABLE children ADD COLUMN care_calendar_url VARCHAR(1000);
        DELETE FROM calendar_sources
        WHERE key IN ('school-otto-stueckrath', 'holidays-he', 'foss')
          AND NOT EXISTS (SELECT 1 FROM calendar_events WHERE calendar_events.source_id = calendar_sources.id);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE children DROP COLUMN care_calendar_url;
        ALTER TABLE children DROP COLUMN care_url;
        ALTER TABLE children DROP COLUMN care_city;
        ALTER TABLE children DROP COLUMN school_calendar_url;
        ALTER TABLE children DROP COLUMN school_url;
        ALTER TABLE children DROP COLUMN school_city;
    """)
