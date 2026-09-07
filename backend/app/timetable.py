"""Weekly school plans: independent of calendar events, evaluated in local school time."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    weekday: int = Field(ge=0, le=6, description="Monday=0, Sunday=6")
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    subject: str = Field(min_length=1, max_length=160)
    room: str = Field(default="", max_length=100)
    teacher: str = Field(default="", max_length=160)
    color: str = Field(default="#3979b8", pattern=r"^#[0-9a-fA-F]{6}$")

    @model_validator(mode="after")
    def duration(self):
        if self.end <= self.start:
            raise ValueError("Das Stundenende muss nach dem Beginn liegen")
        return self


class Timetable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = "Europe/Berlin"
    valid_from: date | None = None
    valid_until: date | None = None
    days_off: list[date] = Field(default_factory=list, max_length=370)
    lessons: list[Lesson] = Field(default_factory=list, max_length=150)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError):
            raise ValueError("Unbekannte Zeitzone")
        return value

    @model_validator(mode="after")
    def validate_plan(self):
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("Das Gültigkeitsende liegt vor dem Beginn")
        self.lessons.sort(key=lambda x: (x.weekday, x.start))
        for first, second in zip(self.lessons, self.lessons[1:]):
            if first.weekday == second.weekday and first.end > second.start:
                raise ValueError("Unterrichtsstunden dürfen sich nicht überschneiden")
        return self


def timetable_status(child, at: datetime, on: date | None = None):
    plan = Timetable.model_validate(child.timetable or {})
    local = at.astimezone(ZoneInfo(plan.timezone))
    today = local.date()
    valid = lambda day: not ((plan.valid_from and day < plan.valid_from) or (plan.valid_until and day > plan.valid_until))
    def daily(day):
        return [x.model_dump() for x in plan.lessons if x.weekday == day.weekday()] if valid(day) and day not in plan.days_off else []
    current_day = daily(today)
    clock = local.strftime("%H:%M")
    current = next((x for x in current_day if x["start"] <= clock < x["end"]), None)
    upcoming = next((x for x in current_day if x["start"] > clock), None)
    if child.timetable is None:
        status, label = "not_configured", "Noch kein Stundenplan hinterlegt"
    elif not valid(today):
        status, label = "outside_validity", "Kein gültiger Stundenplan für heute"
    elif not current_day:
        status, label = "no_school", "Heute kein Unterricht"
    elif current:
        status, label = "lesson", current["subject"]
    elif clock < current_day[0]["start"]:
        status, label = "before_school", f"Unterricht beginnt um {current_day[0]['start']} Uhr"
    elif upcoming:
        status, label = "break", "Pause"
    else:
        status, label = "finished", "Für heute Unterrichtsschluss"
    return {
        "childId": child.id, "childName": child.display_name,
        "status": status, "statusText": label, "evaluatedAt": local.isoformat(),
        "statusDate": today.isoformat(), "date": (on or today).isoformat(), "timezone": plan.timezone,
        "currentLesson": current, "nextLesson": upcoming,
        "dailySchedule": daily(on or today),
        "weeklySchedule": [x.model_dump() for x in plan.lessons],
        "plan": plan.model_dump(mode="json"), "configured": child.timetable is not None,
        "basis": "planned",
    }
