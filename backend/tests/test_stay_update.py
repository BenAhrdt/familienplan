from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.v1.router import stay_request_recipient_id, untouched_stay_ranges, visible_person_ids
from app.models.entities import Role


def test_moving_whole_occurrence_does_not_create_minute_remainder():
    original_start = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)
    original_end = datetime(2026, 9, 22, 14, 30, tzinfo=timezone.utc)

    assert untouched_stay_ranges(
        original_start,
        original_end,
        original_start.replace(minute=31),
        original_end.replace(minute=31),
        preserve_remainder=False,
    ) == []


def test_editing_only_one_day_can_explicitly_preserve_remainder():
    original_start = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)
    original_end = datetime(2026, 9, 23, 14, 30, tzinfo=timezone.utc)
    selected_start = datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc)
    selected_end = datetime(2026, 9, 23, 0, 0, tzinfo=timezone.utc)

    assert untouched_stay_ranges(
        original_start, original_end, selected_start, selected_end, preserve_remainder=True
    ) == [
        (original_start, selected_start),
        (selected_end, original_end),
    ]


def test_new_own_care_request_falls_back_to_default_carer():
    assert stay_request_recipient_id(2, 1, proposed_responsible_user_id=2) == 1


def test_new_care_request_goes_to_proposed_carer():
    assert stay_request_recipient_id(2, 1, proposed_responsible_user_id=3) == 3


def test_handover_is_confirmed_by_the_other_carer():
    assert stay_request_recipient_id(2, 1, current_responsible_user_id=2, proposed_responsible_user_id=3) == 3
    assert stay_request_recipient_id(2, 1, current_responsible_user_id=3, proposed_responsible_user_id=2) == 3


def test_own_deletion_falls_back_to_default_carer():
    assert stay_request_recipient_id(2, 1, current_responsible_user_id=2) == 1


def test_visible_person_ids_only_contains_self_and_explicitly_shared_people():
    user = SimpleNamespace(id=2, role=Role.VIEWER, allowed_person_color_ids=[3, 5])

    assert visible_person_ids(user) == {2, 3, 5}


def test_stay_title_survives_series_regeneration_and_partial_edit():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from starlette.requests import Request
    from app.api.v1.router import create_stay, update_stay, stay_payload
    from app.core.database import Base
    from app.models.entities import Child, Stay, User, PlanStatus
    from app.schemas import StayCreate, StayUpdate

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    request = Request({"type": "http", "method": "POST", "path": "/stays", "headers": [], "client": ("test", 1)})
    with Session(engine, expire_on_commit=False) as db:
        admin = User(username="admin", display_name="Papa", email="admin@example.test",
                     password_hash="x", role=Role.ADMIN, allowed_event_types=["STAY"])
        child = Child(first_name="Emma", display_name="Emma")
        db.add_all([admin, child]); db.flush()
        start, end = datetime(2026, 9, 5), datetime(2026, 9, 7)
        created = create_stay(StayCreate(child_id=child.id, responsible_user_id=admin.id,
            starts_at=start, ends_at=end, status=PlanStatus.CONFIRMED, title="Wochenende",
            note="Sportsachen", recurrence_interval_weeks=1, recurrence_until=datetime(2026, 9, 12)),
            request, db, admin)
        created = [stay_payload(db, row) for row in db.scalars(select(Stay).order_by(Stay.starts_at))]
        assert len(created) == 2
        assert all(item["title"] == "Wochenende" and item["note"] == "Sportsachen" for item in created)
        updated = update_stay(created[0]["id"], StayUpdate(starts_at=start, ends_at=end,
            responsible_user_id=admin.id, title="Bei Papa", note="Sportsachen", scope="series",
            recurrence_interval_weeks=1, recurrence_until=datetime(2026, 9, 19)), request, db, admin)
        assert len(updated) == 3
        assert all(item["title"] == "Bei Papa" for item in updated)
        update_stay(updated[0]["id"], StayUpdate(starts_at=datetime(2026, 9, 6), ends_at=end,
            responsible_user_id=admin.id, title="Ausflug", note="Trinkflasche", scope="occurrence",
            preserve_remainder=True), request, db, admin)
        remainder = db.scalar(select(Stay).where(Stay.starts_at == start))
        assert remainder.title == "Bei Papa"
        assert remainder.note == "Sportsachen"
        edited = db.get(Stay, updated[0]["id"])
        assert edited.title == "Ausflug"
        # Old clients omitting title must not erase it; explicit null clears it.
        for title_fields, expected in [({}, "Ausflug"), ({"title": None}, None)]:
            result = update_stay(edited.id, StayUpdate(starts_at=edited.starts_at, ends_at=edited.ends_at,
                responsible_user_id=admin.id, note=edited.note, scope="occurrence", **title_fields),
                request, db, admin)
            assert result[0]["title"] == expected
