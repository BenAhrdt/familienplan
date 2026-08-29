"""Add the child's default responsible person."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("children", sa.Column("default_responsible_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_children_default_responsible", "children", "users", ["default_responsible_user_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_children_default_responsible", "children", type_="foreignkey")
    op.drop_column("children", "default_responsible_user_id")
