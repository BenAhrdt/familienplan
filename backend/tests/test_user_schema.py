from app.models.entities import Role
from datetime import datetime, timedelta, timezone

from app.api.v1.router import visible_person_ids
from app.models.entities import User
from app.schemas.core import CalendarEventCreate, UserOut


def test_pending_user_internal_email_is_not_exposed_or_rejected():
    user = UserOut(
        id=7,
        username="pending-example",
        display_name="Ohne E-Mail",
        email="pending-example@familienplan.invalid",
        role=Role.VIEWER,
        color="#3BA4E5",
        is_pending=True,
    )

    assert user.email is None
    assert user.allowed_person_color_ids == []


def test_private_calendar_event_type_is_valid():
    start = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    event = CalendarEventCreate(
        title="Persönlicher Termin",
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        event_type="PRIVATE",
        visible_to_user_ids=[],
    )

    assert event.event_type == "PRIVATE"
    assert event.visible_to_user_ids == []


def test_visible_people_include_the_user_and_explicitly_shared_people():
    user = User(id=7, role=Role.EDITOR, allowed_person_color_ids=[11, 13])

    assert visible_person_ids(user) == {7, 11, 13}
