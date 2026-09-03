import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.security import utcnow


class Role(str, enum.Enum):
    VIEWER = "VIEWER"
    EDITOR = "EDITOR"
    ADMIN = "ADMIN"


class Permission(str, enum.Enum):
    VIEW = "VIEW"
    EDIT = "EDIT"


class PlanStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    CHANGE_PROPOSED = "CHANGE_PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    birth_date: Mapped[date | None] = mapped_column(Date)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), default=Role.VIEWER)
    language: Mapped[str] = mapped_column(String(10), default="de")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Berlin")
    color: Mapped[str] = mapped_column(String(7), default="#3BA4E5")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_event_types: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["STAY", "BIRTHDAY", "GENERAL", "SCHOOL"])
    allowed_person_color_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship()


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"))
    display_name: Mapped[str | None] = mapped_column(String(160))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_value: Mapped[str | None] = mapped_column(String(512))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    child_permissions: Mapped[dict[str, str] | None] = mapped_column(JSON)


class Child(Base):
    __tablename__ = "children"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), default="")
    display_name: Mapped[str] = mapped_column(String(160))
    birth_date: Mapped[date | None] = mapped_column(Date)
    school: Mapped[str | None] = mapped_column(String(200))
    school_city: Mapped[str | None] = mapped_column(String(160))
    school_address: Mapped[str | None] = mapped_column(String(500))
    school_state_code: Mapped[str | None] = mapped_column(String(2))
    school_url: Mapped[str | None] = mapped_column(String(1000))
    school_calendar_url: Mapped[str | None] = mapped_column(String(1000))
    school_class: Mapped[str | None] = mapped_column(String(80))
    care: Mapped[str | None] = mapped_column(String(200))
    care_city: Mapped[str | None] = mapped_column(String(160))
    care_url: Mapped[str | None] = mapped_column(String(1000))
    care_calendar_url: Mapped[str | None] = mapped_column(String(1000))
    default_responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(20), default="#426B5E")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ChildUserPermission(Base):
    __tablename__ = "child_user_permissions"
    __table_args__ = (UniqueConstraint("child_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    permission: Mapped[Permission] = mapped_column(Enum(Permission, name="child_permission"))


class CalendarSource(Base):
    __tablename__ = "calendar_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40))
    url: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(Text)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (UniqueConstraint("source_id", "external_id"), Index("ix_events_range", "starts_at", "ends_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_sources.id"))
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id"))
    external_id: Mapped[str | None] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(40), default="FAMILY")
    url: Mapped[str | None] = mapped_column(String(1000))
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    color: Mapped[str | None] = mapped_column(String(7))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str] = mapped_column(String(30), default="GENERAL", index=True)
    custom_type_label: Mapped[str | None] = mapped_column(String(120))
    visible_to_user_ids: Mapped[list[int] | None] = mapped_column(JSON)
    recurrence_group: Mapped[str | None] = mapped_column(String(36), index=True)
    recurrence_frequency: Mapped[str | None] = mapped_column(String(10))
    recurrence_interval: Mapped[int | None] = mapped_column(Integer)
    recurrence_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    attachments: Mapped[list["CalendarEventAttachment"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def attachment_count(self) -> int:
        return len(self.attachments)


class CalendarEventAttachment(Base):
    __tablename__ = "calendar_event_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("calendar_events.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    original_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(80), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event: Mapped[CalendarEvent] = relationship(back_populates="attachments")


class Stay(Base):
    __tablename__ = "stays"
    __table_args__ = (Index("ix_stays_child_range", "child_id", "starts_at", "ends_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), index=True)
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recurrence_rule_id: Mapped[int | None] = mapped_column(ForeignKey("recurrence_rules.id", ondelete="SET NULL"), index=True)
    recurrence_exception_rule_id: Mapped[int | None] = mapped_column(ForeignKey("recurrence_rules.id", ondelete="SET NULL"), index=True)
    recurrence_original_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus, name="plan_status"), default=PlanStatus.DRAFT)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RecurrenceRule(Base):
    __tablename__ = "recurrence_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"))
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rrule: Mapped[str] = mapped_column(String(500))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    until_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HolidayPeriod(Base):
    __tablename__ = "holiday_periods"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    state_code: Mapped[str] = mapped_column(String(2), default="HE")


class HolidayPlan(Base):
    __tablename__ = "holiday_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    holiday_period_id: Mapped[int] = mapped_column(ForeignKey("holiday_periods.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"))
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus, name="plan_status"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class HolidayPlanSegment(Base):
    __tablename__ = "holiday_plan_segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("holiday_plans.id", ondelete="CASCADE"))
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(50))
    object_id: Mapped[int] = mapped_column(Integer)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    affected_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus, name="plan_status"))
    before_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    proposed_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    change_request_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Birthday(Base):
    __tablename__ = "birthdays"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), default="")
    display_name: Mapped[str] = mapped_column(String(160))
    birth_date: Mapped[date] = mapped_column(Date)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_to_user_ids: Mapped[list[int] | None] = mapped_column(JSON)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSON)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ApplicationSetting(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(String(1000))
    secret: Mapped[str] = mapped_column(String(256))
    events: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (UniqueConstraint("channel", "recipient_key", "event_key"), Index("ix_outbox_due", "delivered_at", "available_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20))
    recipient_key: Mapped[str] = mapped_column(String(320))
    event_key: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
