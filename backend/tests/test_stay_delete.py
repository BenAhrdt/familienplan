from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.router import delete_stay
from app.core.database import Base
from app.models.entities import Child, Role, Stay, User


def test_admin_can_delete_stay():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    start = datetime(2026, 9, 4, 18, 7, tzinfo=timezone.utc)

    with Session(engine, expire_on_commit=False) as db:
        admin = User(
            username="admin", display_name="Admin", email="admin@example.test",
            password_hash="test", role=Role.ADMIN,
        )
        child = Child(first_name="Rika", display_name="Rika")
        db.add_all([admin, child])
        db.flush()
        stay = Stay(
            child_id=child.id, responsible_user_id=admin.id,
            starts_at=start, ends_at=start + timedelta(minutes=1),
            created_by_id=admin.id,
        )
        db.add(stay)
        db.commit()
        stay_id = stay.id

        response = delete_stay(
            stay_id,
            "occurrence",
            Request({"type": "http", "method": "DELETE", "path": f"/stays/{stay_id}", "headers": [], "client": ("test", 1)}),
            db=db,
            user=admin,
        )

        assert response.status_code == 204
        assert db.get(Stay, stay_id) is None
