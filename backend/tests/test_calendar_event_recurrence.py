from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.router import create_calendar_event, update_calendar_event
from app.core.database import Base
from app.models.entities import CalendarEvent, Role, User
from app.recurrence import calendar_recurrence_dates
from app.schemas.core import CalendarEventCreate


def request(path: str, method: str = "POST") -> Request:
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "client": ("test", 1),
    })


def event_data(start: datetime, end: datetime) -> CalendarEventCreate:
    return CalendarEventCreate(
        title="Putzfrau",
        starts_at=start,
        ends_at=end,
        event_type="CLEANING",
        recurrence_frequency="WEEKLY",
        recurrence_interval=1,
        recurrence_until=datetime(2026, 11, 16, 22, 59, tzinfo=UTC),
    )


def local_clock(value: datetime) -> tuple[int, int]:
    local = value.astimezone(ZoneInfo("Europe/Berlin"))
    return local.hour, local.minute


def test_recurrence_calculation_keeps_local_time_across_dst_change():
    start = datetime(2026, 10, 19, 5, 15, tzinfo=UTC)  # 07:15 CEST
    end = datetime(2026, 10, 19, 7, 30, tzinfo=UTC)  # 09:30 CEST

    occurrences = calendar_recurrence_dates(
        start,
        end,
        "WEEKLY",
        1,
        until_at=datetime(2026, 11, 9, 22, 59, tzinfo=UTC),
    )

    assert [local_clock(item[0]) for item in occurrences[:3]] == [(7, 15), (7, 15), (7, 15)]
    assert [item[0].astimezone(UTC).hour for item in occurrences[:3]] == [5, 6, 6]
    assert [item[1].astimezone(UTC).hour for item in occurrences[:3]] == [7, 8, 8]


def test_calendar_event_series_uses_local_recurrence_calculation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    start = datetime(2026, 10, 19, 5, 15, tzinfo=UTC)  # 07:15 CEST
    end = datetime(2026, 10, 19, 7, 30, tzinfo=UTC)  # 09:30 CEST

    with Session(engine, expire_on_commit=False) as db:
        admin = User(
            username="admin",
            display_name="Admin",
            email="admin@example.test",
            password_hash="test",
            role=Role.ADMIN,
            allowed_event_types=["CLEANING"],
        )
        db.add(admin)
        db.commit()

        create_calendar_event(event_data(start, end), request("/calendar"), db=db, user=admin)
        events = list(db.scalars(select(CalendarEvent).order_by(CalendarEvent.starts_at)))

        # SQLite drops tzinfo. The later rows still contain the local wall
        # clock values produced by the recurrence helper; PostgreSQL converts
        # those aware values to the corresponding UTC instants.
        assert [(event.starts_at.hour, event.starts_at.minute) for event in events[:3]] == [(5, 15), (7, 15), (7, 15)]


def test_calendar_event_series_update_uses_local_time_across_dst_change():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    start = datetime(2026, 10, 19, 5, 15, tzinfo=UTC)
    end = datetime(2026, 10, 19, 7, 30, tzinfo=UTC)

    with Session(engine, expire_on_commit=False) as db:
        admin = User(
            username="admin",
            display_name="Admin",
            email="admin@example.test",
            password_hash="test",
            role=Role.ADMIN,
            allowed_event_types=["CLEANING"],
        )
        db.add(admin)
        db.commit()

        created = create_calendar_event(event_data(start, end), request("/calendar"), db=db, user=admin)
        update_calendar_event(
            created.id,
            event_data(start, end),
            request(f"/calendar/{created.id}", "PUT"),
            scope="series",
            db=db,
            user=admin,
        )
        events = list(db.scalars(select(CalendarEvent).order_by(CalendarEvent.starts_at)))

        assert [(event.starts_at.hour, event.starts_at.minute) for event in events[:3]] == [(5, 15), (7, 15), (7, 15)]
