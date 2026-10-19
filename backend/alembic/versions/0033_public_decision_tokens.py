"""Passwortlose Entscheidungslinks aus Anfrage-E-Mails

Revision ID: 0033
Revises: 0032
"""

from alembic import op
import sqlalchemy as sa


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_decision_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_request_ids", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_public_decision_tokens_recipient_user_id", "public_decision_tokens", ["recipient_user_id"])
    op.create_index("ix_public_decision_tokens_token_hash", "public_decision_tokens", ["token_hash"])


def downgrade() -> None:
    op.drop_table("public_decision_tokens")
