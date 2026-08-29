"""restore cleaning as an event type

Revision ID: 0014
Revises: 0013
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE calendar_events
        SET event_type = 'CLEANING'
        WHERE lower(title) LIKE '%putzfrau%'
    """)
    op.execute("""
        UPDATE users
        SET allowed_event_types = (allowed_event_types::jsonb || '[\"CLEANING\"]'::jsonb)::json
        WHERE id IN (
            SELECT DISTINCT created_by_id
            FROM calendar_events
            WHERE event_type = 'CLEANING' AND created_by_id IS NOT NULL
        )
        AND NOT allowed_event_types::jsonb @> '[\"CLEANING\"]'::jsonb
    """)


def downgrade():
    op.execute("UPDATE calendar_events SET event_type = 'GENERAL' WHERE event_type = 'CLEANING'")
    op.execute("UPDATE users SET allowed_event_types = (allowed_event_types::jsonb - 'CLEANING')::json")
