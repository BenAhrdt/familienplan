import hashlib
import hmac
import json
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import utcnow
from app.models.entities import ApplicationSetting, CalendarEvent, OutboxMessage, PlanStatus, Stay, User, WebhookEndpoint


def mail_config(db):
    row = db.get(ApplicationSetting, "mail")
    value = dict(row.value or {}) if row else {}
    env = get_settings()
    return {
        "enabled": value.get("enabled", False),
        "host": value.get("host") or env.smtp_host,
        "port": int(value.get("port") or env.smtp_port),
        "username": value.get("username") or env.smtp_username,
        "password": value.get("password") or env.smtp_password,
        "from_address": value.get("from_address") or env.smtp_from,
        "app_url": (value.get("app_url") or env.app_origin).rstrip("/"),
        "security": value.get("security") or ("starttls" if value.get("starttls", env.smtp_starttls) else "none"),
    }


def queue_mail(db, user_id: int, event_key: str, event_type: str, subject: str, body: str, action_url: str | None = None):
    user = db.get(User, user_id)
    config = mail_config(db)
    if not user or user.is_pending or not user.email or not config["enabled"]:
        return
    if event_type == "notification.created":
        now = utcnow()
        digest = db.scalar(select(OutboxMessage).where(
            OutboxMessage.channel == "email",
            OutboxMessage.recipient_key == user.email,
            OutboxMessage.event_type == "notification.digest",
            OutboxMessage.delivered_at.is_(None),
            OutboxMessage.attempts == 0,
        ).order_by(OutboxMessage.created_at.desc()).limit(1).with_for_update())
        entry = {"subject": subject, "body": body, "action_url": action_url}
        if digest:
            entries = [*digest.payload.get("entries", []), entry]
            digest.payload = {
                "subject": f"{len(entries)} neue Benachrichtigungen in FamilienPlan",
                "body": "\n\n".join(f"• {item['subject']}\n{item['body']}" for item in entries),
                "action_url": config["app_url"],
                "entries": entries,
            }
            digest.available_at = min(now + timedelta(minutes=2), digest.created_at + timedelta(minutes=10))
        else:
            db.add(OutboxMessage(channel="email", recipient_key=user.email,
                event_key=f"notification-digest:{user_id}:{event_key}", event_type="notification.digest",
                available_at=now + timedelta(minutes=2),
                payload={"subject": subject, "body": body, "action_url": action_url, "entries": [entry]}))
        return
    db.add(OutboxMessage(channel="email", recipient_key=user.email, event_key=event_key,
                         event_type=event_type, payload={"subject": subject, "body": body, "action_url": action_url}))


def queue_webhooks(db, event_key: str, event_type: str, data: dict):
    envelope = {"api_version": "v1", "id": event_key, "type": event_type,
                "occurred_at": utcnow().isoformat(), "data": data}
    for hook in db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))):
        if hook.events and "*" not in hook.events and event_type not in hook.events:
            continue
        if not db.scalar(select(OutboxMessage.id).where(OutboxMessage.channel == "webhook",
                OutboxMessage.recipient_key == str(hook.id), OutboxMessage.event_key == event_key)):
            db.add(OutboxMessage(channel="webhook", recipient_key=str(hook.id), event_key=event_key,
                                 event_type=event_type, payload=envelope))


def _send_mail(config: dict, recipient: str, payload: dict):
    message = EmailMessage()
    message["Subject"] = payload["subject"]
    message["From"] = config["from_address"]
    message["To"] = recipient
    message.set_content(payload["body"])
    if payload.get("action_url"):
        import html
        subject, body, url = (html.escape(str(payload[key])) for key in ("subject", "body", "action_url"))
        message.add_alternative(f'''<!doctype html><html><body style="margin:0;background:#f5f6f2;font-family:Arial,sans-serif;color:#23332e"><div style="max-width:600px;margin:30px auto;background:white;border:1px solid #dfe5e0;border-radius:14px;padding:32px"><h1 style="font-family:Georgia,serif;font-size:28px">{subject}</h1><p style="line-height:1.6;white-space:pre-line">{body}</p><p style="margin-top:28px"><a href="{url}" style="display:inline-block;background:#3ba4e5;color:white;text-decoration:none;font-weight:bold;padding:13px 18px;border-radius:9px">Vorschlag in FamilienPlan öffnen</a></p><p style="margin-top:24px;color:#708079;font-size:12px">Falls der Button nicht funktioniert:<br>{url}</p></div></body></html>''', subtype="html")
    smtp_class = smtplib.SMTP_SSL if config.get("security") == "ssl" else smtplib.SMTP
    with smtp_class(config["host"], config["port"], timeout=15) as smtp:
        if config.get("security") == "starttls":
            smtp.starttls()
        if config["username"]:
            smtp.login(config["username"], config["password"] or "")
        smtp.send_message(message)


async def deliver_outbox_once():
    with SessionLocal() as db:
        now, since = utcnow(), utcnow() - timedelta(hours=24)
        for stay in db.scalars(select(Stay).where(Stay.status == PlanStatus.CONFIRMED,
                Stay.starts_at >= since, Stay.starts_at <= now)):
            queue_webhooks(db, f"stay:{stay.id}:started:{stay.starts_at.isoformat()}", "stay.started",
                           {"type":"stay","id":stay.id,"child_id":stay.child_id,"responsible_user_id":stay.responsible_user_id,"starts_at":stay.starts_at.isoformat(),"ends_at":stay.ends_at.isoformat()})
        for stay in db.scalars(select(Stay).where(Stay.status == PlanStatus.CONFIRMED,
                Stay.ends_at >= since, Stay.ends_at <= now)):
            queue_webhooks(db, f"stay:{stay.id}:ended:{stay.ends_at.isoformat()}", "stay.ended",
                           {"type":"stay","id":stay.id,"child_id":stay.child_id,"responsible_user_id":stay.responsible_user_id,"starts_at":stay.starts_at.isoformat(),"ends_at":stay.ends_at.isoformat()})
        for event in db.scalars(select(CalendarEvent).where(CalendarEvent.is_private.is_(False),
                CalendarEvent.starts_at >= since, CalendarEvent.starts_at <= now)):
            kind = "school_holiday" if event.category == "HOLIDAY" else "school_event" if event.category == "SCHOOL" else "appointment"
            queue_webhooks(db, f"calendar:{event.id}:started:{event.starts_at.isoformat()}", f"{kind}.started",
                           {"type":kind,"event_type":event.event_type,"custom_type_label":event.custom_type_label,
                            "id":event.id,"child_id":event.child_id,"title":event.title,
                            "starts_at":event.starts_at.isoformat(),"ends_at":event.ends_at.isoformat()})
        db.flush()
        due = list(db.scalars(select(OutboxMessage).where(
            OutboxMessage.delivered_at.is_(None), OutboxMessage.available_at <= utcnow(),
            OutboxMessage.attempts < 8).order_by(OutboxMessage.id).limit(20).with_for_update(skip_locked=True)))
        config = mail_config(db)
        for item in due:
            try:
                if item.channel == "email":
                    if not config["host"]:
                        raise RuntimeError("Kein SMTP-Server konfiguriert")
                    import asyncio
                    await asyncio.to_thread(_send_mail, config, item.recipient_key, item.payload)
                else:
                    hook = db.get(WebhookEndpoint, int(item.recipient_key))
                    if not hook or not hook.is_active:
                        item.delivered_at = utcnow()
                        continue
                    raw = json.dumps(item.payload, separators=(",", ":"), ensure_ascii=False).encode()
                    signature = hmac.new(hook.secret.encode(), raw, hashlib.sha256).hexdigest()
                    async with httpx.AsyncClient(timeout=15) as client:
                        response = await client.post(hook.url, content=raw, headers={
                            "Content-Type": "application/json", "X-FamilienPlan-Event": item.event_type,
                            "X-FamilienPlan-Signature": f"sha256={signature}"})
                        response.raise_for_status()
                item.delivered_at = utcnow()
                item.last_error = None
            except Exception as exc:
                item.attempts += 1
                item.last_error = str(exc)[:1000]
                item.available_at = utcnow() + timedelta(seconds=min(3600, 15 * (2 ** item.attempts)))
        db.commit()
