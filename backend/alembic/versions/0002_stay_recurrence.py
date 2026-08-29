"""Materialized recurring stays.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recurrence_rules", sa.Column("until_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stays", sa.Column("recurrence_rule_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_stays_recurrence_rule", "stays", "recurrence_rules", ["recurrence_rule_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_stays_recurrence_rule_id", "stays", ["recurrence_rule_id"])


def downgrade() -> None:
    op.drop_index("ix_stays_recurrence_rule_id", table_name="stays")
    op.drop_constraint("fk_stays_recurrence_rule", "stays", type_="foreignkey")
    op.drop_column("stays", "recurrence_rule_id")
    op.drop_column("recurrence_rules", "until_at")
