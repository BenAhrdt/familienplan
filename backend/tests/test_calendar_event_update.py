from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.router import update_calendar_event
from app.core.database import Base
from app.models.entities import CalendarEvent, Child, Role, User
from app.schemas.core import CalendarEventCreate


def test_calendar_event_update_persists_new_child_assignment():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    start = datetime(2026, 9, 12, tzinfo=timezone.utc)
    with Session(engine, expire_on_commit=False) as db:
        admin = User(
            username="admin", display_name="Admin", email="admin@example.test",
            password_hash="test", role=Role.ADMIN,
            allowed_event_types=["GENERAL"],
        )
        child = Child(first_name="Rika", display_name="Rika")
        db.add_all([admin, child])
        db.flush()
        event = CalendarEvent(
            title="Testeintrag", starts_at=start, ends_at=start + timedelta(hours=1),
            event_type="GENERAL", category="FAMILY", created_by_id=admin.id,
        )
        db.add(event)
        db.commit()
        event_id = event.id

        updated = update_calendar_event(
            event_id,
            CalendarEventCreate(
                title="Testeintrag", starts_at=start, ends_at=start + timedelta(hours=1),
                event_type="GENERAL", category="FAMILY", child_id=child.id,
            ),
            Request({"type": "http", "method": "PUT", "path": f"/calendar/{event_id}", "headers": [], "client": ("test", 1)}),
            db=db,
            user=admin,
        )

        assert updated.child_id == child.id
        db.expire_all()
        assert db.get(CalendarEvent, event_id).child_id == child.id
