from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.integration_router import PersonTokenCreate, allowed_children, create_person_api_token, person_api_tokens, revoke_person_api_token
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
