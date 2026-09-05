from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.integration_router import PersonTokenCreate, allowed_children, api_context, create_person_api_token, default_stay_periods, person_api_tokens, revoke_person_api_token
from app.core.database import Base
from app.models.entities import Child, ChildUserPermission, Permission, Role, User


def test_token_child_scope_cannot_restore_revoked_user_access():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="viewer", display_name="Viewer", email="viewer@example.test", password_hash="x", role=Role.VIEWER)
        allowed = Child(first_name="Rika", display_name="Rika")
        denied = Child(first_name="Tom", display_name="Tom")
        db.add_all([user, allowed, denied]); db.flush()
        db.add(ChildUserPermission(user_id=user.id, child_id=allowed.id, permission=Permission.VIEW)); db.commit()
        token = SimpleNamespace(scopes=[f"child:{allowed.id}", f"child:{denied.id}"])

        assert allowed_children(token, user, db) == {allowed.id}


def test_person_can_have_independently_revocable_named_api_tokens():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        admin = User(username="admin", display_name="Admin", email="admin@example.test", password_hash="x", role=Role.ADMIN)
        person = User(username="person", display_name="Person", email="person@example.test", password_hash="x", role=Role.VIEWER, is_pending=False)
        db.add_all([admin, person]); db.commit()

        first = create_person_api_token(person.id, PersonTokenCreate(name="ioBroker"), db=db, _=admin)
        second = create_person_api_token(person.id, PersonTokenCreate(name="Home Assistant"), db=db, _=admin)
        assert {item["name"] for item in person_api_tokens(person.id, db=db, _=admin)} == {"ioBroker", "Home Assistant"}

        revoke_person_api_token(person.id, first["id"], db=db, _=admin)
        assert [item["name"] for item in person_api_tokens(person.id, db=db, _=admin)] == ["Home Assistant"]
        assert first["token"] != second["token"]


def test_new_person_token_authenticates_immediately():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        admin = User(username="admin", display_name="Admin", email="admin@example.test", password_hash="x", role=Role.ADMIN)
        person = User(username="person", display_name="Person", email="person@example.test", password_hash="x", role=Role.VIEWER, is_pending=False)
        db.add_all([admin, person]); db.commit()

        created = create_person_api_token(person.id, PersonTokenCreate(name="ioBroker"), db=db, _=admin)
        request = SimpleNamespace(headers={"Authorization": f"Bearer {created['token']}"})
        token, authenticated_user = api_context(request, db)

        assert created["token"].startswith(f"fp_{token.id}_")
        assert authenticated_user.id == person.id


def test_default_stays_fill_only_gaps_around_explicit_stays():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 4, tzinfo=UTC)
    child = SimpleNamespace(id=7, display_name="Emma", default_responsible_user_id=11)
    stay = SimpleNamespace(
        child_id=7,
        starts_at=datetime(2026, 9, 2, tzinfo=UTC),
        ends_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    periods = default_stay_periods(child, [stay], start, end, "Papa")

    assert [(item["starts_at"], item["ends_at"]) for item in periods] == [
        (start, stay.starts_at),
        (stay.ends_at, end),
    ]
    assert all(item["title"] == "(Standard) Emma bei Papa" and item["description"] is None for item in periods)
    assert all(item["event_type"] == "STAY" for item in periods)
    assert all(item["source"] == "default" and item["generated"] for item in periods)


def test_calendar_separates_stay_titles_notes_and_default_titles():
    from app.api.v1.integration_router import integration_events
    from app.models.entities import Stay, PlanStatus

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        person = User(username="papa", display_name="Papa", email="papa@example.test", password_hash="x", role=Role.ADMIN)
        db.add(person); db.flush()
        child = Child(first_name="Emma", display_name="Emma", default_responsible_user_id=person.id)
        db.add(child); db.flush()
        start, end = datetime(2026, 9, 5), datetime(2026, 9, 6)
        stay = Stay(child_id=child.id, responsible_user_id=person.id, created_by_id=person.id,
                    starts_at=start.replace(hour=8), ends_at=start.replace(hour=18),
                    status=PlanStatus.CONFIRMED, title="Nachmittag bei Papa", note="Sportsachen mitgeben")
        db.add(stay); db.commit()
        token = SimpleNamespace(scopes=["read:stays"])
        result = integration_events(start, end, child_id=child.id, context=(token, person), db=db)
        assert [item["title"] for item in result] == [
            "(Standard) Emma bei Papa", "Nachmittag bei Papa", "(Standard) Emma bei Papa",
        ]
        assert [item["description"] for item in result] == [None, "Sportsachen mitgeben", None]
        stay.title = None
        db.commit()
        result = integration_events(start, end, child_id=child.id, context=(token, person), db=db)
        assert result[1]["title"] == "Emma bei Papa"
        assert result[1]["description"] == "Sportsachen mitgeben"
