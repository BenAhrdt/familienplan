"""Allow link-only invitations with child permissions."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("invitations", "email", existing_type=sa.String(320), nullable=True)
    op.add_column("invitations", sa.Column("child_permissions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.execute("DELETE FROM invitations WHERE email IS NULL")
    op.drop_column("invitations", "child_permissions")
    op.alter_column("invitations", "email", existing_type=sa.String(320), nullable=False)
