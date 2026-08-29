"""Add separately managed birthdays."""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "birthdays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_birthdays_created_by_id", "birthdays", ["created_by_id"])


def downgrade() -> None:
    op.drop_index("ix_birthdays_created_by_id", table_name="birthdays")
    op.drop_table("birthdays")
