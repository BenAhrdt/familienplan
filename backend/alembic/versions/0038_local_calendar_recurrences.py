"""Keep recurring calendar events at their local wall-clock time.

Before this migration, occurrences after a daylight-saving transition were
created by adding a fixed number of seconds to the UTC timestamp. Repair the
stored occurrences from the first event in each series so existing series are
corrected along with newly created ones.
"""

from collections import defaultdict

from alembic import op
import sqlalchemy as sa

from app.recurrence import calendar_recurrence_dates


revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT id, recurrence_group, starts_at, ends_at,
               recurrence_frequency, recurrence_interval, recurrence_until
        FROM calendar_events
        WHERE recurrence_group IS NOT NULL
        ORDER BY recurrence_group, starts_at, id
    """)).mappings().all()
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["recurrence_group"]].append(row)

    for group_rows in groups.values():
        template = group_rows[0]
        occurrences = calendar_recurrence_dates(
            template["starts_at"],
            template["ends_at"],
            template["recurrence_frequency"],
            template["recurrence_interval"],
            until_at=template["recurrence_until"],
        )
        if not occurrences:
            continue

        for row in group_rows:
            current_start = row["starts_at"]
            # Use the nearest generated instant. This also repairs a series
            # with an explicitly removed occurrence, where row order no longer
            # matches the ordinal of the recurrence.
            start, end = min(
                occurrences,
                key=lambda candidate: abs((candidate[0] - current_start).total_seconds()),
            )
            if row["starts_at"] == start and row["ends_at"] == end:
                continue
            connection.execute(
                sa.text("""
                    UPDATE calendar_events
                    SET starts_at = :starts_at, ends_at = :ends_at
                    WHERE id = :id
                """),
                {"id": row["id"], "starts_at": start, "ends_at": end},
            )


def downgrade() -> None:
    # The migration repairs data and there is no safe inverse: the former UTC
    # timestamps are not distinguishable from intentionally edited events.
    pass
