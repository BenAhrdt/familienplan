"""preserve moved occurrences while rebuilding a stay series

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("stays", sa.Column("recurrence_exception_rule_id", sa.Integer(), nullable=True))
    op.add_column("stays", sa.Column("recurrence_original_start", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_stays_recurrence_exception_rule_id", "stays", ["recurrence_exception_rule_id"])
    op.create_foreign_key(
        "fk_stays_recurrence_exception_rule_id", "stays", "recurrence_rules",
        ["recurrence_exception_rule_id"], ["id"], ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_stays_recurrence_exception_rule_id", "stays", type_="foreignkey")
    op.drop_index("ix_stays_recurrence_exception_rule_id", table_name="stays")
    op.drop_column("stays", "recurrence_original_start")
    op.drop_column("stays", "recurrence_exception_rule_id")
