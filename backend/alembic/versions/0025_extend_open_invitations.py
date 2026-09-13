"""Extend open invitations to the new 30-day validity period."""

from alembic import op


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE invitations
        SET expires_at = CURRENT_TIMESTAMP + INTERVAL '30 days'
        WHERE used_at IS NULL
          AND token_value IS NOT NULL
          AND expires_at < CURRENT_TIMESTAMP + INTERVAL '30 days'
        """
    )


def downgrade():
    # The previous individual expiry timestamps cannot be reconstructed safely.
    pass
