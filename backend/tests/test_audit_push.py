from types import SimpleNamespace

from app.api.v1 import router
from app.models.entities import ApplicationSetting, AuditLog, Role, User


class FakeDb:
    def __init__(self, users, settings):
        self.users = users
        self.settings = settings

    def scalars(self, _query):
        return self.users

    def get(self, model, key):
        if model is ApplicationSetting and str(key).startswith("audit_push_"):
            user_id = int(str(key).removeprefix("audit_push_"))
            return SimpleNamespace(value=self.settings.get(user_id, {"enabled": False}))
        return None


def admin(user_id, name):
    return User(id=user_id, username=name.lower(), display_name=name, email=f"{name.lower()}@example.test", password_hash="x", role=Role.ADMIN, is_active=True)


def request(approved=False):
    return SimpleNamespace(state=SimpleNamespace(approved_change=approved))


def test_audit_push_is_only_queued_for_enabled_other_admins(monkeypatch):
    actor = admin(1, "Ben")
    enabled_recipient = admin(2, "Anna")
    disabled_recipient = admin(3, "Chris")
    db = FakeDb([enabled_recipient, disabled_recipient], {2: {"enabled": True}})
    queued = []
    monkeypatch.setattr(router, "queue_push", lambda *args: queued.append(args))

    router.queue_audit_pushes(db, request(), AuditLog(id=42, user_id=1, action="CALENDAR_EVENT_CHANGED"), actor)

    assert len(queued) == 1
    assert queued[0][1:4] == (2, "audit:42", "Logbuch: Ben")
    assert queued[0][4] == "Ben hat einen Termin geändert."


def test_default_audit_push_skips_authentication_requests_and_approved_changes(monkeypatch):
    actor = admin(1, "Ben")
    db = FakeDb([admin(2, "Anna")], {2: {"enabled": True}})
    queued = []
    monkeypatch.setattr(router, "queue_push", lambda *args: queued.append(args))

    router.queue_audit_pushes(db, request(), AuditLog(id=1, user_id=1, action="LOGIN"), actor)
    router.queue_audit_pushes(db, request(), AuditLog(id=4, user_id=1, action="APP_OPENED"), actor)
    router.queue_audit_pushes(db, request(), AuditLog(id=2, user_id=1, action="STAY_CHANGE_PROPOSED"), actor)
    router.queue_audit_pushes(db, request(approved=True), AuditLog(id=3, user_id=1, action="STAY_CHANGED"), actor)

    assert queued == []


def test_audit_push_rules_filter_person_and_allow_selected_app_open(monkeypatch):
    friederike = admin(1, "Friederike")
    anna = admin(3, "Anna")
    db = FakeDb([admin(2, "Ben")], {2: {"enabled": True, "user_ids": [1], "actions": ["APP_OPENED"]}})
    queued = []
    monkeypatch.setattr(router, "queue_push", lambda *args: queued.append(args))

    router.queue_audit_pushes(db, request(), AuditLog(id=4, user_id=1, action="APP_OPENED"), friederike)
    router.queue_audit_pushes(db, request(), AuditLog(id=5, user_id=3, action="APP_OPENED"), anna)
    router.queue_audit_pushes(db, request(), AuditLog(id=6, user_id=1, action="CALENDAR_EVENT_CHANGED"), friederike)

    assert len(queued) == 1
    assert queued[0][1:5] == (2, "audit:4", "Logbuch: Friederike", "Friederike hat FamilienPlan geöffnet.")


def test_app_open_is_logged_for_a_session_without_recent_entry(monkeypatch):
    db = SimpleNamespace(scalar=lambda _query: None)
    logged = []
    monkeypatch.setattr(router, "audit", lambda *args: logged.append(args))

    created = router.audit_app_opened(db, request(), admin(1, "Friederike"), SimpleNamespace(id=17))

    assert created is True
    assert logged[0][2:5] == ("APP_OPENED", 1, ("session", "17"))


def test_app_open_is_not_logged_again_within_debounce_window(monkeypatch):
    db = SimpleNamespace(scalar=lambda _query: 99)
    logged = []
    monkeypatch.setattr(router, "audit", lambda *args: logged.append(args))

    created = router.audit_app_opened(db, request(), admin(1, "Friederike"), SimpleNamespace(id=17))

    assert created is False
    assert logged == []
