from calendar import monthrange
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def _local(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def calendar_recurrence_dates(
    starts_at: datetime,
    ends_at: datetime,
    frequency: str | None,
    interval: int | None,
    day_of_month: int | None = None,
    until_at: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """Return recurring timestamps while keeping the local wall-clock time.

    Datetimes are persisted as instants (UTC in PostgreSQL), but a calendar
    recurrence describes a local time such as every Monday at 07:15. Doing the
    recurrence arithmetic on UTC timestamps changes that local time when the
    daylight-saving offset changes. The date calculation therefore happens on
    naive local calendar values and each generated occurrence is localized only
    after its date and time have been determined.
    """
    occurrences = [(starts_at, ends_at)]
    if not frequency or not interval:
        return occurrences

    timezone = ZoneInfo(get_settings().app_timezone)
    local_start = _local(starts_at, timezone)
    local_end = _local(ends_at, timezone)
    start_wall = local_start.replace(tzinfo=None)
    end_wall = local_end.replace(tzinfo=None)
    duration = end_wall - start_wall
    limit_wall = (
        _local(until_at, timezone).replace(tzinfo=None)
        if until_at
        else start_wall + timedelta(days=366 * 5)
    )
    requested_day = day_of_month or start_wall.day
    cursor = start_wall

    while True:
        if frequency == "MONTHLY":
            month_index = cursor.month - 1 + interval
            year, month = cursor.year + month_index // 12, month_index % 12 + 1
            cursor = cursor.replace(
                year=year,
                month=month,
                day=min(requested_day, monthrange(year, month)[1]),
            )
        else:
            cursor += timedelta(weeks=interval)
        if cursor > limit_wall:
            break
        occurrence_start = cursor.replace(tzinfo=timezone)
        occurrence_end = (cursor + duration).replace(tzinfo=timezone)
        occurrences.append((occurrence_start, occurrence_end))

    return occurrences
