"""Einzelne Standardkalender und einmalige Anmeldelinks aus E-Mails

Revision ID: 0036
Revises: 0035
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
import hashlib
import secrets


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_login_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("redirect_path", sa.String(length=1000), nullable=False, server_default="/calendar"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_email_login_tokens_user_id", "email_login_tokens", ["user_id"])
    op.create_index("ix_email_login_tokens_token_hash", "email_login_tokens", ["token_hash"])
    op.create_index("ix_email_login_tokens_expires_at", "email_login_tokens", ["expires_at"])

    # Existing installations get the same separate feeds as newly created
    # users. The raw feed token is needed for calendar apps and is already the
    # established storage model for calendar feeds.
    feed_types = [
        ("STAY", "Betreuung"),
        ("SCHOOL", "Schule"),
        ("GENERAL", "Allgemein"),
        ("BIRTHDAY", "Geburtstage"),
        ("CLEANING", "Putzfrau"),
        ("WASTE", "Abfall"),
        ("SCHOOL_HOLIDAY", "Ferien / Feiertage"),
        ("PRIVATE", "Privat"),
        ("OTHER", "Sonstiges"),
    ]
    default_user_types = ["STAY", "BIRTHDAY", "GENERAL", "SCHOOL"]
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("role", sa.String()),
        sa.column("allowed_event_types", sa.JSON()),
    )
    feeds = sa.table(
        "calendar_feeds",
        sa.column("user_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("event_types", sa.JSON()),
        sa.column("stay_visibility", sa.JSON()),
        sa.column("token_hash", sa.String()),
        sa.column("token_value", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    for user_id, role, allowed_value in connection.execute(sa.select(users.c.id, users.c.role, users.c.allowed_event_types)):
        role_name = str(role).rsplit(".", 1)[-1]
        allowed = set(allowed_value if allowed_value is not None else default_user_types)
        if role_name == "ADMIN":
            visible = [event_type for event_type, _ in feed_types]
        else:
            allowed.add("PRIVATE")
            if "SCHOOL" in allowed:
                allowed.add("SCHOOL_HOLIDAY")
            if "OTHER" in allowed:
                allowed.add("OTHER")
            visible = [event_type for event_type, _ in feed_types if event_type in allowed]
        existing = connection.execute(
            sa.select(feeds.c.event_types).where(feeds.c.user_id == user_id)
        ).scalars()
        existing_types = {frozenset(value or []) for value in existing}
        for event_type, name in feed_types:
            if event_type not in visible or frozenset({event_type}) in existing_types:
                continue
            raw = secrets.token_urlsafe(48)
            connection.execute(feeds.insert().values(
                user_id=user_id,
                name=name,
                event_types=[event_type],
                stay_visibility=["OWN"],
                token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                token_value=raw,
                created_at=datetime.now(timezone.utc),
            ))
            existing_types.add(frozenset({event_type}))


def downgrade() -> None:
    op.drop_table("email_login_tokens")
