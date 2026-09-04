import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush
from sqlalchemy import select

from app.core.security import utcnow
from app.models.entities import ApplicationSetting, OutboxMessage, PushSubscription


def vapid_config(db) -> dict[str, str]:
    row = db.get(ApplicationSetting, "web_push_vapid")
    if row and row.value.get("private_key") and row.value.get("public_key"):
        return dict(row.value)
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    value = {
        "private_key": private_pem,
        "public_key": base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode(),
    }
    if row:
        row.value = value
    else:
        db.add(ApplicationSetting(key="web_push_vapid", value=value))
    db.flush()
    return value


def queue_push(db, user_id: int, event_key: str, title: str, body: str, action_url: str):
    for subscription in db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)):
        db.add(OutboxMessage(
            channel="push", recipient_key=str(subscription.id), event_key=event_key,
            event_type="notification.created",
            payload={"title": title, "body": body, "url": action_url, "subscription_id": subscription.id},
        ))


def deliver_push(db, item: OutboxMessage, app_origin: str):
    subscription = db.get(PushSubscription, int(item.payload["subscription_id"]))
    if not subscription:
        item.delivered_at = utcnow()
        return
    vapid = vapid_config(db)
    try:
        webpush(
            subscription_info={"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
            data=json.dumps(item.payload, ensure_ascii=False),
            vapid_private_key=vapid["private_key"],
            vapid_claims={"sub": app_origin},
            timeout=15,
        )
        subscription.last_used_at = utcnow()
        item.delivered_at = utcnow()
        item.last_error = None
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in {404, 410}:
            db.delete(subscription)
            item.delivered_at = utcnow()
            item.last_error = "Push-Abonnement war nicht mehr gültig und wurde entfernt."
            return
        raise
