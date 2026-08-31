from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.router import _ics_datetime, deduplicate_school_candidates, remove_legacy_school_imports, school_event_matches_class
from app.core.database import Base
from app.models.entities import CalendarEvent, CalendarSource, Child, User


def test_all_day_ics_dates_use_application_timezone():
    start, all_day = _ics_datetime("20261019")
    end, _ = _ics_datetime("20261020")
    assert all_day is True
    assert start.isoformat() == "2026-10-19T00:00:00+02:00"
    assert end.isoformat() == "2026-10-20T00:00:00+02:00"


def test_school_event_class_filter_keeps_matching_and_school_wide_events():
    assert school_event_matches_class("3a Elternabend", None, "3A")
    assert school_event_matches_class("Schulfest für alle Klassen", None, "3A")
    assert school_event_matches_class("Schultheater der Länder – Theater AG 4", None, "3A")
    assert school_event_matches_class("Projekttag", None, "3A")


def test_school_event_class_filter_rejects_other_classes_and_understands_groups():
    assert not school_event_matches_class("3c Elternabend", None, "3A")
    assert not school_event_matches_class("4 a/b Klassenfahrt", None, "3A")
    assert school_event_matches_class("3 a/b Ausflug", None, "3A")
    assert school_event_matches_class("Klassenstufe 3 Sportfest", None, "3A")
    assert not school_event_matches_class("Jahrgang 4 Sportfest", None, "3A")


def test_legacy_school_cleanup_preserves_manual_events():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with Session(engine) as db:
        user = User(
            username="parent", display_name="Parent", email="parent@example.test",
            password_hash="test", role="ADMIN",
        )
        child = Child(first_name="Kind", display_name="Kind")
        current = CalendarSource(key="child-1-school", name="Aktuell", kind="SCHOOL")
        old = CalendarSource(key="legacy-school", name="Alt", kind="SCHOOL")
        db.add_all([user, child, current, old])
        db.flush()
        imported = CalendarEvent(
            source_id=old.id, child_id=child.id, external_id="old-uid",
            title="Alter Import", starts_at=now, ends_at=now, category="SCHOOL", event_type="SCHOOL",
        )
        orphaned_import = CalendarEvent(
            child_id=child.id, external_id="orphan-uid", title="Verwaister Import",
            starts_at=now, ends_at=now, category="SCHOOL", event_type="SCHOOL",
        )
        manual = CalendarEvent(
            child_id=child.id, created_by_id=user.id, title="Manueller Schultermin",
            starts_at=now, ends_at=now, category="SCHOOL", event_type="SCHOOL",
        )
        db.add_all([imported, orphaned_import, manual])
        db.flush()
        manual_id = manual.id

        assert remove_legacy_school_imports(db, child.id, current.id) == 2
        db.flush()
        assert db.get(CalendarEvent, manual_id) is not None


def test_school_feed_deduplication_prefers_shorter_overlapping_entry():
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    candidates = [
        {"order": 0, "external_id": "old", "title": "Klassenfahrt", "starts_at": start, "ends_at": start.replace(day=5)},
        {"order": 1, "external_id": "current", "title": " Klassenfahrt ", "starts_at": start, "ends_at": start.replace(day=2)},
        {"order": 2, "external_id": "later", "title": "Klassenfahrt", "starts_at": start.replace(day=10), "ends_at": start.replace(day=11)},
    ]

    result = deduplicate_school_candidates(candidates)

    assert [item["external_id"] for item in result] == ["current", "later"]
