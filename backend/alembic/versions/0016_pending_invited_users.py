"""represent invited people before account activation

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_pending", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("invitations", sa.Column("token_value", sa.String(length=512), nullable=True))
    op.add_column("invitations", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_invitations_user_id", "invitations", ["user_id"])
    op.create_foreign_key("fk_invitations_user_id", "invitations", "users", ["user_id"], ["id"], ondelete="CASCADE")


def downgrade():
    op.drop_constraint("fk_invitations_user_id", "invitations", type_="foreignkey")
    op.drop_constraint("uq_invitations_user_id", "invitations", type_="unique")
    op.drop_column("invitations", "user_id")
    op.drop_column("invitations", "token_value")
    op.drop_column("users", "is_pending")
