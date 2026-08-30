import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.entities import Permission, PlanStatus, Role


class SetupStatus(BaseModel):
    setup_required: bool


class SetupAdmin(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    password: str = Field(min_length=12, max_length=256)
    password_confirm: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("Die Passwörter stimmen nicht überein")
        return self


class Login(BaseModel):
    username: str
    password: str
    remember: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr
    role: Role
    color: str
    birth_date: date | None = None
    allowed_event_types: list[str] = ["STAY", "BIRTHDAY", "GENERAL", "SCHOOL"]
    is_pending: bool = False


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str
    impersonating: bool = False


class InvitationCreate(BaseModel):
    email: EmailStr | None = None
    role: Role = Role.VIEWER
    display_name: str = Field(min_length=2, max_length=160)
    child_permissions: dict[int, Permission] = {}
    send_email: bool = False


class InvitationOut(BaseModel):
    id: int
    email: EmailStr | None
    expires_at: datetime
    invite_url: str
    user_id: int | None = None
    used_at: datetime | None = None


class InvitationAccept(SetupAdmin):
    token: str


class ChildCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    display_name: str = Field(min_length=1, max_length=160)
    birth_date: date | None = None
    school: str | None = None
    school_city: str | None = None
    school_address: str | None = None
    school_state_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    school_url: str | None = None
    school_calendar_url: str | None = None
    school_class: str | None = None
    care: str | None = None
    care_city: str | None = None
    care_url: str | None = None
    care_calendar_url: str | None = None
    default_responsible_user_id: int | None = None
    notes: str | None = None


class ChildUpdate(ChildCreate):
    pass


class InstitutionResult(BaseModel):
    name: str
    city: str | None = None
    address: str | None = None
    state_code: str | None = None
    website: str | None = None
    calendar_url: str | None = None


class ChildOut(ChildCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool


class PermissionSet(BaseModel):
    user_id: int
    permission: Permission


class PersonAccessUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=2, max_length=160)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr
    role: Role
    child_permissions: dict[int, Permission] = {}
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    birth_date: date | None = None
    allowed_event_types: list[str] = ["STAY", "BIRTHDAY", "GENERAL", "SCHOOL"]


class ProfileUpdate(BaseModel):
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    birth_date: date | None = None


class PersonAccessOut(BaseModel):
    user: UserOut
    child_permissions: dict[int, Permission]


class StayCreate(BaseModel):
    child_id: int
    responsible_user_id: int
    starts_at: datetime
    ends_at: datetime
    status: PlanStatus = PlanStatus.DRAFT
    note: str | None = None
    recurrence_interval_weeks: int | None = Field(default=None, ge=1, le=52)
    recurrence_frequency: str = Field(default="WEEKLY", pattern="^(WEEKLY|MONTHLY)$")
    recurrence_day_of_month: int | None = Field(default=None, ge=1, le=31)
    recurrence_until: datetime | None = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Das Ende muss nach dem Beginn liegen")
        return self


class StayOut(StayCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_by_id: int
    recurrence_rule_id: int | None = None
    responsible_display_name: str | None = None


class GroupPlanningItem(BaseModel):
    child_id: int
    responsible_user_id: int
    starts_at: datetime
    ends_at: datetime
    name: str = Field(min_length=1, max_length=300)
    kind: str = Field(pattern="^(FERIEN|FEIERTAG|BRUECKENTAG|FREI)$")

    @model_validator(mode="after")
    def valid_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Das Ende muss nach dem Beginn liegen")
        return self


class GroupPlanningCreate(BaseModel):
    title: str = Field(default="Gemeinsame Planung", min_length=2, max_length=200)
    affected_user_id: int | None = None
    items: list[GroupPlanningItem] = Field(min_length=1, max_length=200)


class StayUpdate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    responsible_user_id: int
    note: str | None = None
    recurrence_interval_weeks: int | None = Field(default=None, ge=1, le=52)
    recurrence_frequency: str | None = Field(default=None, pattern="^(WEEKLY|MONTHLY)$")
    recurrence_day_of_month: int | None = Field(default=None, ge=1, le=31)
    recurrence_until: datetime | None = None
    scope: str = Field(pattern="^(occurrence|future|series)$")

    @model_validator(mode="after")
    def valid_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Das Ende muss nach dem Beginn liegen")
        return self


class ChangeDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT|COUNTER)$")
    counter_proposal: StayUpdate | dict | None = None
    comment: str | None = Field(default=None, max_length=1000)
    item_comments: dict[str, str] = {}

    @model_validator(mode="after")
    def rejection_requires_comment(self):
        if self.decision == "REJECT" and not (self.comment or "").strip() and not any(value.strip() for value in self.item_comments.values()):
            raise ValueError("Bitte gib eine Begründung für die Ablehnung an")
        if self.comment is not None:
            self.comment = self.comment.strip()
        self.item_comments = {key: value.strip() for key, value in self.item_comments.items() if value.strip()}
        return self


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    title: str
    body: str
    read_at: datetime | None
    created_at: datetime


class BirthdayCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=160)
    birth_date: date
    is_private: bool = False
    visible_to_user_ids: list[int] | None = None


class BirthdayOut(BirthdayCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_by_id: int
    event_type: str = "BIRTHDAY"


class ChangeRequestOut(BaseModel):
    id: int
    object_type: str
    object_id: int
    requested_by_id: int
    requested_by_name: str
    affected_user_id: int
    affected_user_name: str
    status: PlanStatus
    proposed_data: dict
    before_data: dict
    child_id: int | None = None
    child_name: str | None = None
    created_at: datetime


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    all_day: bool = False
    category: str = Field(default="FAMILY", pattern="^(FAMILY|SCHOOL|FOSS|HOLIDAY)$")
    child_id: int | None = None
    color: str = Field(default="#8B6CC1", pattern=r"^#[0-9A-Fa-f]{6}$")
    is_private: bool = False
    event_type: str = Field(default="GENERAL", pattern="^(STAY|BIRTHDAY|GENERAL|SCHOOL|CLEANING|WASTE|OTHER)$")
    custom_type_label: str | None = Field(default=None, max_length=120)
    visible_to_user_ids: list[int] | None = None
    recurrence_frequency: str | None = Field(default=None, pattern="^(WEEKLY|MONTHLY)$")
    recurrence_interval: int | None = Field(default=None, ge=1, le=52)
    recurrence_day_of_month: int | None = Field(default=None, ge=1, le=31)
    recurrence_until: datetime | None = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Das Ende muss nach dem Beginn liegen")
        if self.event_type == "OTHER" and not (self.custom_type_label or "").strip():
            raise ValueError("Für den Typ Sonstiges ist eine Bezeichnung erforderlich")
        if self.event_type != "OTHER":
            self.custom_type_label = None
        return self


class CalendarEventOut(CalendarEventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_id: int | None = None
    created_by_id: int | None = None
    recurrence_group: str | None = None
    color: str | None = None
    raw_data: dict | None = None


class HolidayOut(BaseModel):
    name: str
    starts_on: date
    ends_on: date


class ThemeSetting(BaseModel):
    primary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    holiday_color: str = Field(default="#78B98B", pattern=r"^#[0-9A-Fa-f]{6}$")
    birthday_color: str = Field(default="#E0A526", pattern=r"^#[0-9A-Fa-f]{6}$")
    school_color: str = Field(default="#3979B8", pattern=r"^#[0-9A-Fa-f]{6}$")


class SectionAccessSetting(BaseModel):
    birthdays: list[int] = []
    waste_collection: list[int] = []


class WasteCalendarSetting(BaseModel):
    enabled: bool = False
    provider: str = Field(default="AWIDO", pattern="^(AWIDO|ICAL)$")
    customer: str = Field(default="awld", max_length=80)
    city: str = Field(default="Hohenahr", max_length=160)
    street: str = Field(default="Ahrdt", max_length=200)
    calendar_url: str = Field(default="", max_length=1500)
    color: str = Field(default="#5C8B58", pattern=r"^#[0-9A-Fa-f]{6}$")
    type_colors: dict[str, str] = {
        "bio": "#795548", "yellow": "#E4B820", "residual": "#4F5963",
        "paper": "#3979B8", "hazardous": "#B33A3A", "other": "#5C8B58",
    }
    visible_to_user_ids: list[int] = []
    last_sync_at: str | None = None
    last_result: dict | None = None
    last_error: str | None = None

    @field_validator("type_colors")
    @classmethod
    def valid_type_colors(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not re.fullmatch(r"#[0-9A-Fa-f]{6}", color) for color in value.values()):
            raise ValueError("Alle Farben müssen im Format #RRGGBB angegeben werden")
        return value


class CalendarColorPreferences(BaseModel):
    holiday_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    birthday_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    school_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    waste_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
