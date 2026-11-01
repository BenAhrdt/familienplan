"""Unbefristete Anmeldelinks aus E-Mails

Revision ID: 0037
Revises: 0036
"""

from alembic import op
import sqlalchemy as sa


revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "email_login_tokens",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.execute(sa.text("UPDATE email_login_tokens SET expires_at = NULL"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE email_login_tokens SET expires_at = now() + interval '14 days'"))
    op.alter_column(
        "email_login_tokens",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
