from types import SimpleNamespace

from app.api.v1 import router
from app.models.entities import ApplicationSetting, AuditLog, Role, User


class FakeDb:
    def __init__(self, users, enabled_user_ids):
        self.users = users
        self.enabled_user_ids = enabled_user_ids

    def scalars(self, _query):
        return self.users

    def get(self, model, key):
        if model is ApplicationSetting and str(key).startswith("audit_push_"):
            user_id = int(str(key).removeprefix("audit_push_"))
            return SimpleNamespace(value={"enabled": user_id in self.enabled_user_ids})
        return None


def admin(user_id, name):
    return User(id=user_id, username=name.lower(), display_name=name, email=f"{name.lower()}@example.test", password_hash="x", role=Role.ADMIN, is_active=True)


def request(approved=False):
    return SimpleNamespace(state=SimpleNamespace(approved_change=approved))


def test_audit_push_is_only_queued_for_enabled_other_admins(monkeypatch):
    actor = admin(1, "Ben")
    enabled_recipient = admin(2, "Anna")
    disabled_recipient = admin(3, "Chris")
    db = FakeDb([enabled_recipient, disabled_recipient], {2})
    queued = []
    monkeypatch.setattr(router, "queue_push", lambda *args: queued.append(args))

    router.queue_audit_pushes(db, request(), AuditLog(id=42, user_id=1, action="CALENDAR_EVENT_CHANGED"), actor)

    assert len(queued) == 1
    assert queued[0][1:4] == (2, "audit:42", "Logbuch: Ben")
    assert queued[0][4] == "Ben hat einen Termin geändert."


def test_audit_push_skips_logins_requests_and_approved_changes(monkeypatch):
    actor = admin(1, "Ben")
    db = FakeDb([admin(2, "Anna")], {2})
    queued = []
    monkeypatch.setattr(router, "queue_push", lambda *args: queued.append(args))

    router.queue_audit_pushes(db, request(), AuditLog(id=1, user_id=1, action="LOGIN"), actor)
    router.queue_audit_pushes(db, request(), AuditLog(id=2, user_id=1, action="STAY_CHANGE_PROPOSED"), actor)
    router.queue_audit_pushes(db, request(approved=True), AuditLog(id=3, user_id=1, action="STAY_CHANGED"), actor)

    assert queued == []
