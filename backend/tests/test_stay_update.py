from datetime import datetime, timezone

from app.api.v1.router import untouched_stay_ranges


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
