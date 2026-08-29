"""school event type defaults and imported event backfill

Revision ID: 0013
Revises: 0012
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE users
        SET allowed_event_types = (allowed_event_types::jsonb || '[\"SCHOOL\"]'::jsonb)::json
        WHERE NOT allowed_event_types::jsonb @> '[\"SCHOOL\"]'::jsonb
    """)
    op.execute("UPDATE calendar_events SET event_type = 'SCHOOL' WHERE category = 'SCHOOL'")
    op.alter_column("users", "allowed_event_types", server_default='["STAY", "BIRTHDAY", "GENERAL", "SCHOOL"]')


def downgrade():
    op.execute("UPDATE calendar_events SET event_type = 'GENERAL' WHERE event_type = 'SCHOOL'")
    op.execute("""
        UPDATE users
        SET allowed_event_types = (allowed_event_types::jsonb - 'SCHOOL')::json
    """)
    op.alter_column("users", "allowed_event_types", server_default='["STAY", "BIRTHDAY", "GENERAL"]')
