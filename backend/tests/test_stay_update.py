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
