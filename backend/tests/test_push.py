import base64

from app.models.entities import ApplicationSetting, PushSubscription
from app.push import queue_push, vapid_config


class FakeDb:
    def __init__(self, subscriptions=None):
        self.setting = None
        self.subscriptions = subscriptions or []
        self.added = []

    def get(self, model, key):
        if model is ApplicationSetting and key == "web_push_vapid":
            return self.setting
        return None

    def add(self, item):
        self.added.append(item)
        if isinstance(item, ApplicationSetting):
            self.setting = item

    def flush(self):
        pass

    def scalars(self, _query):
        return self.subscriptions


def test_vapid_key_is_valid_and_reused():
    db = FakeDb()
    first = vapid_config(db)
    second = vapid_config(db)
    encoded = first["public_key"] + "=" * ((4 - len(first["public_key"]) % 4) % 4)
    assert len(base64.urlsafe_b64decode(encoded)) == 65
    assert first == second
    assert "PRIVATE KEY" in first["private_key"]


def test_push_is_queued_for_each_registered_device():
    subscriptions = [PushSubscription(id=11, user_id=7, endpoint="https://push.example/1", p256dh="p" * 20, auth="a" * 8)]
    db = FakeDb(subscriptions)
    queue_push(db, 7, "notification:4", "Neue Anfrage", "Bitte prüfen", "https://family.example/calendar?request=3")
    queued = db.added[0]
    assert queued.channel == "push"
    assert queued.recipient_key == "11"
    assert queued.payload["url"].endswith("request=3")
