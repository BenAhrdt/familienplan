from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.integration_router import allowed_children
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
