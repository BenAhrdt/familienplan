from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1 import integration_router
from app.api.v1.integration_router import CalendarFeedCreate, calendar_feed_events, calendar_feed_ics, create_calendar_feed, filter_calendar_feed_events
from app.core.database import Base
from app.models.entities import CalendarFeed, Child, Role, User


def test_calendar_feed_is_named_and_secret_is_returned_only_on_creation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(username="person", display_name="Person", email="person@example.test", password_hash="x")
        db.add(user)
        db.commit()

        result = create_calendar_feed(CalendarFeedCreate(name="iPhone"), db=db, user=user)

        assert result["name"] == "iPhone"
        assert "STAY" in result["event_types"]
        assert result["stay_visibility"] == ["OWN"]
        assert result["url"].endswith(".ics")
        assert "/calendar-feeds/" in result["url"]
        assert db.scalar(CalendarFeed.__table__.select().where(CalendarFeed.id == result["id"])) is not None


def test_calendar_feed_ics_escapes_values_and_keeps_all_day_events():
    event = {
        "source": "event",
        "event_type": "GENERAL",
        "id": 7,
        "child_id": None,
        "starts_at": datetime(2026, 10, 18, tzinfo=UTC),
        "ends_at": datetime(2026, 10, 19, tzinfo=UTC),
        "all_day": True,
        "title": "Sommer;fest, Familie",
        "description": "Mitbringen\nDecke",
    }

    ics = calendar_feed_ics([event], "Familienkalender")

    assert "BEGIN:VCALENDAR\r\n" in ics
    assert "X-WR-CALNAME:Familienkalender\r\n" in ics
    assert "DTSTART;VALUE=DATE:20261018\r\n" in ics
    assert "DTEND;VALUE=DATE:20261019\r\n" in ics
    assert "SUMMARY:Sommer\\;fest\\, Familie\r\n" in ics
    assert "DESCRIPTION:Mitbringen\\nDecke\r\n" in ics
    assert ics.endswith("END:VCALENDAR\r\n")


def test_calendar_feed_can_filter_visible_event_types_per_device():
    events = [
        {"event_type": "STAY", "title": "Betreuung"},
        {"event_type": "WASTE", "title": "Abfall"},
        {"event_type": "GENERAL", "title": "Allgemein"},
    ]

    assert [item["title"] for item in filter_calendar_feed_events(events, ["STAY", "GENERAL"])] == ["Betreuung", "Allgemein"]


def test_calendar_feed_uses_owner_as_default_for_generated_standard_care(monkeypatch):
    monkeypatch.setattr(
        integration_router,
        "integration_events",
        lambda *args, **kwargs: [
            {"event_type": "STAY", "source": "default", "child_id": 1, "responsible_user_id": 2, "title": "Standardbetreuung"},
            {"event_type": "STAY", "source": "stay", "child_id": 1, "responsible_user_id": 1, "title": "Bei mir"},
        ],
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="person", display_name="Person", email="person@example.test", password_hash="x")
        default_person = User(username="standard", display_name="Standard", email="standard@example.test", password_hash="x")
        db.add_all([user, default_person]); db.flush()
        db.add(Child(id=1, first_name="Rika", display_name="Rika", default_responsible_user_id=default_person.id)); db.commit()

        feed = CalendarFeed(name="Betreuung", event_types=["STAY"], stay_visibility=["OWN"])
        events = calendar_feed_events(feed, user, datetime(2026, 10, 1), datetime(2026, 10, 20), db)

        assert [item["title"] for item in events] == ["Bei mir"]

        feed.stay_visibility = ["STANDARD"]
        events = calendar_feed_events(feed, user, datetime(2026, 10, 1), datetime(2026, 10, 20), db)

        assert [item["title"] for item in events] == ["Standardbetreuung"]


def test_calendar_feed_selects_own_standard_and_other_stays(monkeypatch):
    monkeypatch.setattr(
        integration_router,
        "integration_events",
        lambda *args, **kwargs: [
            {"event_type": "STAY", "source": "stay", "child_id": 1, "responsible_user_id": 2, "title": "Bei Standardperson"},
            {"event_type": "STAY", "source": "stay", "child_id": 1, "responsible_user_id": 1, "title": "Bei mir"},
            {"event_type": "STAY", "source": "stay", "child_id": 1, "responsible_user_id": 3, "title": "Bei anderer Person"},
        ],
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="person", display_name="Person", email="person@example.test", password_hash="x")
        default_person = User(username="standard", display_name="Standard", email="standard@example.test", password_hash="x")
        other_person = User(username="other", display_name="Andere", email="other@example.test", password_hash="x")
        db.add_all([user, default_person, other_person]); db.flush()
        db.add(Child(id=1, first_name="Rika", display_name="Rika", default_responsible_user_id=default_person.id)); db.commit()

        feed = CalendarFeed(name="Betreuung", event_types=["STAY"], stay_visibility=["OWN"])
        events = calendar_feed_events(
            feed,
            user,
            datetime(2026, 10, 1),
            datetime(2026, 10, 20),
            db,
        )
        assert [item["title"] for item in events] == ["Bei mir"]

        feed.stay_visibility = ["STANDARD", "OTHER"]
        events = calendar_feed_events(
            feed,
            user,
            datetime(2026, 10, 1),
            datetime(2026, 10, 20),
            db,
        )

        assert [item["title"] for item in events] == ["Bei Standardperson", "Bei anderer Person"]


def test_calendar_feed_includes_generated_school_holidays(monkeypatch):
    monkeypatch.setattr(integration_router, "integration_events", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        integration_router,
        "_fetch_school_holiday_rows",
        lambda state, year: [{
            "name": [{"language": "DE", "text": "Herbstferien"}],
            "startDate": "2026-10-05",
            "endDate": "2026-10-17",
        }] if state == "HE" and year == 2026 else [],
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(username="admin", display_name="Admin", email="admin@example.test", password_hash="x", role=Role.ADMIN)
        child = Child(first_name="Rika", display_name="Rika", school_state_code="HE")
        db.add_all([user, child]); db.flush()
        feed = CalendarFeed(user_id=user.id, name="Ferien", event_types=["SCHOOL_HOLIDAY"], token_hash="token")
        db.add(feed); db.commit()

        events = calendar_feed_events(
            feed,
            user,
            datetime(2026, 10, 1, tzinfo=UTC),
            datetime(2026, 10, 20, tzinfo=UTC),
            db,
        )

        assert [(item["title"], item["event_type"], item["all_day"]) for item in events] == [
            ("Herbstferien", "SCHOOL_HOLIDAY", True),
        ]
        ics = calendar_feed_ics(events, feed.name)
        assert "CATEGORIES:SCHOOL_HOLIDAY\r\n" in ics
        assert "DTSTART;VALUE=DATE:20261005\r\n" in ics
        assert "DTEND;VALUE=DATE:20261018\r\n" in ics
