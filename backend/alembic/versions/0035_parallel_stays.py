"""Bewusst parallele Betreuungszeiten markieren

Revision ID: 0035
Revises: 0034
"""

from alembic import op
import sqlalchemy as sa


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stays", sa.Column("parallel", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text("""
        UPDATE stays AS s
        SET parallel = TRUE
        FROM change_requests AS r
        WHERE r.proposed_data->>'action' = 'CREATE'
          AND r.proposed_data->>'parallel' = 'true'
          AND (
              s.id = r.object_id
              OR EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements_text(COALESCE(r.proposed_data->'stay_ids', '[]'::jsonb)) AS ids(stay_id)
                  WHERE ids.stay_id::integer = s.id
              )
          )
    """))
    op.alter_column("stays", "parallel", server_default=None)


def downgrade() -> None:
    op.drop_column("stays", "parallel")
