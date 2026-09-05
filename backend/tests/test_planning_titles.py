from datetime import datetime
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.router import create_planning_group, decide_change_request
from app.core.database import Base
from app.models.entities import Child, User, Role, Stay, PlanStatus
from app.schemas import GroupPlanningCreate, GroupPlanningItem, ChangeDecision


@pytest.mark.parametrize("mode", ["direct", "proposal"])
def test_planning_uses_title_including_counter_proposal(mode):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    request = Request({"type": "http", "method": "POST", "path": "/planning-groups", "headers": [], "client": ("test", 1)})
    with Session(engine, expire_on_commit=False) as db:
        admin = User(username="admin", display_name="Papa", email="papa@example.test", password_hash="x", role=Role.ADMIN)
        other = User(username="other", display_name="Mama", email="mama@example.test", password_hash="x", role=Role.ADMIN)
        child = Child(first_name="Emma", display_name="Emma")
        db.add_all([admin, other, child]); db.flush()
        entry = GroupPlanningItem(child_id=child.id, responsible_user_id=admin.id,
                                  starts_at=datetime(2026, 10, 5), ends_at=datetime(2026, 10, 10),
                                  name="Herbstferien", kind="FERIEN")
        result = create_planning_group(GroupPlanningCreate(affected_user_id=other.id, items=[entry]),
                                       request, mode, db, admin)
        stay = db.scalar(select(Stay))
        assert stay.title == "Herbstferien"
        assert stay.note is None
        if mode == "proposal":
            counter_entry = entry.model_dump(mode="json")
            counter_entry["name"] = "Herbstferien bei Papa"
            decide_change_request(result["request_id"], ChangeDecision(decision="COUNTER",
                counter_proposal={"action": "GROUP_CREATE", "items": [counter_entry]}),
                request, db, other)
            stay = db.scalar(select(Stay))
            assert stay.title == "Herbstferien bei Papa"
            assert stay.note is None
            decide_change_request(result["request_id"], ChangeDecision(decision="APPROVE"),
                                  request, db, admin)
            assert stay.status == PlanStatus.CONFIRMED
            assert stay.title == "Herbstferien bei Papa"
            assert stay.note is None
