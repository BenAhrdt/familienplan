"""enable waste collection type for administrators

Revision ID: 0015
Revises: 0014
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE users
        SET allowed_event_types = (allowed_event_types::jsonb || '[\"WASTE\"]'::jsonb)::json
        WHERE role = 'ADMIN' AND NOT allowed_event_types::jsonb @> '[\"WASTE\"]'::jsonb
    """)


def downgrade():
    op.execute("UPDATE users SET allowed_event_types = (allowed_event_types::jsonb - 'WASTE')::json WHERE role = 'ADMIN'")
