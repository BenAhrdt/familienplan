import smtplib
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import quote, urlsplit, urlunsplit

from itsdangerous import URLSafeSerializer
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import new_token, token_hash, utcnow
from app.models.entities import ApplicationSetting, CalendarFeed, ChangeRequest, EmailLoginToken, OutboxMessage, PlanStatus, PublicDecisionToken, Role, User


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


DEFAULT_CALENDAR_FEED_TYPES = [
    "STAY", "SCHOOL", "GENERAL", "BIRTHDAY", "CLEANING", "WASTE",
    "SCHOOL_HOLIDAY", "PRIVATE", "OTHER",
]
DEFAULT_CALENDAR_FEED_NAMES = {
    "STAY": "Betreuung",
    "SCHOOL": "Schule",
    "GENERAL": "Allgemein",
    "BIRTHDAY": "Geburtstage",
    "CLEANING": "Putzfrau",
    "WASTE": "Abfall",
    "SCHOOL_HOLIDAY": "Ferien / Feiertage",
    "PRIVATE": "Privat",
    "OTHER": "Sonstiges",
}
DEFAULT_USER_EVENT_TYPES = ["STAY", "BIRTHDAY", "GENERAL", "SCHOOL"]
calendar_feed_fallback_tokens = URLSafeSerializer(get_settings().secret_key, salt="familienplan-calendar-feed")


def default_calendar_feed_event_types(user: User) -> list[str]:
    """Return the separate feed categories currently visible to a user."""
    if user.role == Role.ADMIN:
        return list(DEFAULT_CALENDAR_FEED_TYPES)
    allowed = set(user.allowed_event_types if user.allowed_event_types is not None else DEFAULT_USER_EVENT_TYPES)
    allowed.add("PRIVATE")
    if "SCHOOL" in allowed:
        allowed.add("SCHOOL_HOLIDAY")
    if "OTHER" in allowed:
        allowed.add("OTHER")
    return [event_type for event_type in DEFAULT_CALENDAR_FEED_TYPES if event_type in allowed]


def ensure_default_calendar_feeds(db, user: User) -> list[CalendarFeed]:
    """Create one stable, single-category feed for every visible category."""
    visible_types = default_calendar_feed_event_types(user)
    rows = list(db.scalars(select(CalendarFeed).where(CalendarFeed.user_id == user.id)))
    active_rows = [row for row in rows if row.revoked_at is None]
    for event_type in visible_types:
        if any(set(row.event_types or []) == {event_type} for row in active_rows):
            continue
        raw = new_token()
        row = CalendarFeed(
            user_id=user.id,
            name=DEFAULT_CALENDAR_FEED_NAMES[event_type],
            event_types=[event_type],
            stay_visibility=["OWN"],
            token_hash=token_hash(raw),
            token_value=raw,
        )
        db.add(row)
        db.flush()
        active_rows.append(row)
    visible_sets = {frozenset({event_type}) for event_type in visible_types}
    return sorted(
        (row for row in active_rows if frozenset(row.event_types or []) in visible_sets),
        key=lambda row: DEFAULT_CALENDAR_FEED_TYPES.index((row.event_types or [""])[0]),
    )


def _calendar_feed_token(row: CalendarFeed) -> str:
    return row.token_value or calendar_feed_fallback_tokens.dumps({"feed_id": row.id})


def calendar_feed_links(db, user: User, app_url: str) -> list[dict[str, str]]:
    """Return the user's separate feed links, creating missing defaults first."""
    rows = ensure_default_calendar_feeds(db, user)
    base_url = app_url.rstrip("/")
    return [
        {
            "name": row.name,
            "url": f"{base_url}/api/v1/calendar-feeds/{quote(_calendar_feed_token(row), safe='')}.ics",
        }
        for row in rows
    ]


def _safe_redirect_path(action_url: str | None, app_url: str) -> str:
    """Keep email-login redirects on the configured FamilienPlan origin."""
    fallback = "/calendar"
    if not action_url:
        return fallback
    target = urlsplit(str(action_url))
    origin = urlsplit(app_url)
    if target.scheme or target.netloc:
        if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
            return fallback
    if not target.path.startswith("/"):
        return fallback
    return urlunsplit(("", "", target.path, target.query, target.fragment))


def email_login_url(db, user: User, action_url: str | None, config: dict) -> str:
    """Create a reusable, time-limited sign-in URL for a trusted recipient."""
    raw = new_token()
    db.add(EmailLoginToken(
        user_id=user.id,
        token_hash=token_hash(raw),
        redirect_path=_safe_redirect_path(action_url, config["app_url"]),
        expires_at=utcnow() + timedelta(days=14),
    ))
    return f"{config['app_url'].rstrip('/')}/api/v1/auth/email-login/{quote(raw, safe='')}"


def _public_decision_url(db, user_id: int, targets: list[dict], decision: str, config: dict) -> str:
    raw = new_token()
    request_ids = sorted({int(target["request_id"]) for target in targets})
    db.add(PublicDecisionToken(
        token_hash=token_hash(raw),
        recipient_user_id=user_id,
        change_request_ids=request_ids,
        target_items=targets,
        decision=decision,
    ))
    return f"{config['app_url']}/api/v1/public/decision/{raw}"


def _decision_actions(db, user_id: int, request_ids: list[int], config: dict) -> list[dict]:
    actions = []
    for request_id in sorted(set(request_ids)):
        item = db.get(ChangeRequest, request_id)
        if not item or item.affected_user_id != user_id or item.status not in {PlanStatus.PROPOSED, PlanStatus.CHANGE_PROPOSED}:
            continue
        proposed = item.proposed_data or {}
        if proposed.get("action") == "GROUP_CREATE":
            for index, entry in enumerate(proposed.get("items") or []):
                if entry.get("email_decision"):
                    continue
                target = {"request_id": item.id, "item_index": index}
                actions.append({
                    **target,
                    "label": f"Abschnitt {index + 1}: {entry.get('name') or 'Zeitraum'}",
                    "approve_url": _public_decision_url(db, user_id, [target], "APPROVE", config),
                    "reject_url": _public_decision_url(db, user_id, [target], "REJECT", config),
                })
        else:
            target = {"request_id": item.id}
            actions.append({
                **target,
                "approve_url": _public_decision_url(db, user_id, [target], "APPROVE", config),
                "reject_url": _public_decision_url(db, user_id, [target], "REJECT", config),
            })
    return actions


def _batch_decision_actions(db, user_id: int, entries: list[dict], config: dict) -> list[dict]:
    targets = []
    seen = set()
    for entry in entries:
        for action in entry.get("decision_actions", []):
            if action.get("request_id") is None:
                continue
            target = {"request_id": int(action["request_id"])}
            if action.get("item_index") is not None:
                target["item_index"] = int(action["item_index"])
            key = tuple(sorted(target.items()))
            if key not in seen:
                seen.add(key)
                targets.append(target)
    if len(targets) < 2:
        return []
    return [
        {"label": "Alle bestätigen", "url": _public_decision_url(db, user_id, targets, "APPROVE", config)},
        {"label": "Alle ablehnen", "url": _public_decision_url(db, user_id, targets, "REJECT", config)},
    ]


def queue_mail(
    db,
    user_id: int,
    event_key: str,
    event_type: str,
    subject: str,
    body: str,
    action_url: str | None = None,
    decision_request_ids: list[int] | None = None,
):
    user = db.get(User, user_id)
    config = mail_config(db)
    if not user or user.is_pending or not user.email or not config["enabled"]:
        return
    if event_type == "notification.created":
        now = utcnow()
        decision_actions = _decision_actions(db, user_id, decision_request_ids or [], config)
        digest = db.scalar(select(OutboxMessage).where(
            OutboxMessage.channel == "email",
            OutboxMessage.recipient_key == user.email,
            OutboxMessage.event_type == "notification.digest",
            OutboxMessage.delivered_at.is_(None),
            OutboxMessage.attempts == 0,
        ).order_by(OutboxMessage.created_at.desc()).limit(1).with_for_update())
        calendar_links = calendar_feed_links(db, user, config["app_url"])
        login_url = digest.payload.get("login_url") if digest else None
        if action_url and not login_url:
            login_url = email_login_url(db, user, action_url, config)
        entry = {"subject": subject, "body": body, "action_url": action_url, "decision_actions": decision_actions}
        if digest:
            entries = [*digest.payload.get("entries", []), entry]
            digest.payload = {
                "subject": f"{len(entries)} neue Benachrichtigungen in FamilienPlan",
                "body": "\n\n".join(f"• {item['subject']}\n{item['body']}" for item in entries),
                "action_url": config["app_url"],
                "entries": entries,
                "decision_batch_actions": _batch_decision_actions(db, user_id, entries, config),
                "event_type": "notification.digest",
                "calendar_links": digest.payload.get("calendar_links") or calendar_links,
                "login_url": login_url,
            }
            created_at = digest.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=now.tzinfo)
            digest.available_at = min(now + timedelta(minutes=2), created_at + timedelta(minutes=10))
        else:
            db.add(OutboxMessage(channel="email", recipient_key=user.email,
                event_key=f"notification-digest:{user_id}:{event_key}", event_type="notification.digest",
                available_at=now + timedelta(minutes=2),
                payload={
                    "subject": subject,
                    "body": body,
                    "action_url": action_url,
                    "entries": [entry],
                    "decision_batch_actions": _batch_decision_actions(db, user_id, [entry], config),
                    "event_type": "notification.digest",
                    "calendar_links": calendar_links,
                    "login_url": login_url,
                }))
        return
    if event_type == "notification.resend":
        decision_actions = _decision_actions(db, user_id, decision_request_ids or [], config)
        entry = {"subject": subject, "body": body, "action_url": action_url, "decision_actions": decision_actions}
        calendar_links = calendar_feed_links(db, user, config["app_url"])
        login_url = email_login_url(db, user, action_url, config) if action_url else None
        db.add(OutboxMessage(channel="email", recipient_key=user.email, event_key=event_key,
                             event_type=event_type, payload={
                                 "subject": subject,
                                 "body": body,
                                 "action_url": action_url,
                                 "entries": [entry],
                                 "decision_batch_actions": _batch_decision_actions(db, user_id, [entry], config),
                                 "event_type": event_type,
                                 "calendar_links": calendar_links,
                                 "login_url": login_url,
                             }))
        return
    calendar_links = [] if event_type == "password.reset" else calendar_feed_links(db, user, config["app_url"])
    login_url = email_login_url(db, user, action_url, config) if action_url and event_type != "password.reset" else None
    db.add(OutboxMessage(channel="email", recipient_key=user.email, event_key=event_key,
                         event_type=event_type, payload={"subject": subject, "body": body, "action_url": action_url,
                         "event_type": event_type, "calendar_links": calendar_links, "login_url": login_url}))


def queue_mail_batch(db, user_id: int, event_key: str, event_type: str, entries: list[dict], subject: str | None = None):
    """Queue one mail containing several request entries for one recipient."""
    user = db.get(User, user_id)
    config = mail_config(db)
    if not user or user.is_pending or not user.email or not config["enabled"] or not entries:
        return
    normalized = []
    for raw_entry in entries:
        copy_to_self = bool(raw_entry.get("copy_to_self"))
        decision_actions = [] if copy_to_self else _decision_actions(
            db, user_id, raw_entry.get("decision_request_ids") or [], config
        )
        normalized.append({
            "subject": raw_entry["subject"],
            "body": raw_entry["body"],
            "action_url": raw_entry.get("action_url"),
            "decision_actions": decision_actions,
        })
    if not normalized:
        return
    # The batch endpoint has already collected the selected entries, so there
    # is no remaining digest window to wait for. Automatic single notifications
    # keep their delay in queue_mail above.
    is_digest = event_type == "notification.created"
    if subject is None:
        if is_digest:
            subject = f"{len(normalized)} neue Anfragen in FamilienPlan"
        elif len(normalized) == 1:
            subject = normalized[0]["subject"]
        else:
            subject = f"{len(normalized)} erneute Betreuungsanfragen"
    now = utcnow()
    action_url = next((entry.get("action_url") for entry in normalized if entry.get("action_url")), config["app_url"])
    calendar_links = [] if event_type == "password.reset" else calendar_feed_links(db, user, config["app_url"])
    login_url = email_login_url(db, user, action_url, config) if event_type != "password.reset" else None
    db.add(OutboxMessage(
        channel="email",
        recipient_key=user.email,
        event_key=event_key,
        event_type=event_type,
        available_at=now + timedelta(minutes=2) if is_digest else now,
        payload={
            "subject": subject,
            "body": "\n\n".join(f"• {entry['subject']}\n{entry['body']}" for entry in normalized),
            "action_url": action_url,
            "entries": normalized,
            "decision_batch_actions": _batch_decision_actions(db, user_id, normalized, config),
            "event_type": event_type,
            "calendar_links": calendar_links,
            "login_url": login_url,
        },
    ))


def _send_mail(config: dict, recipient: str, payload: dict):
    message = EmailMessage()
    message["Subject"] = payload["subject"]
    message["From"] = config["from_address"]
    message["To"] = recipient
    plain_body = payload["body"]
    login_url = payload.get("login_url")
    calendar_links = payload.get("calendar_links") or []
    if payload.get("event_type") in {"notification.digest", "notification.resend"}:
        links = []
        for entry in payload.get("entries", []):
            for action in entry.get("decision_actions", []):
                label = f"{action['label']} – " if action.get("label") else ""
                links.extend([
                    f"{entry.get('subject', 'Anfrage')} – {label}Bestätigen: {action['approve_url']}",
                    f"{entry.get('subject', 'Anfrage')} – {label}Ablehnen: {action['reject_url']}",
                ])
        for action in payload.get("decision_batch_actions", []):
            links.append(f"{action['label']}: {action['url']}")
        if links:
            plain_body = f"{plain_body}\n\nDirekte Entscheidungen:\n" + "\n".join(links)
    if login_url:
        plain_body = (
            f"{plain_body}\n\nDirekt in FamilienPlan öffnen (ohne Passwort):\n{login_url}"
            "\nDieser Link ist 14 Tage ab Versand gültig und kann in dieser Zeit mehrfach ohne Passwort verwendet werden."
        )
    if calendar_links:
        plain_body = f"{plain_body}\n\nKalender abonnieren:\n" + "\n".join(
            f"{item.get('name', 'Kalender')}: {item.get('url', '')}" for item in calendar_links
        )
    message.set_content(plain_body)
    if payload.get("action_url"):
        import html
        subject, body, action_url = (html.escape(str(payload[key])) for key in ("subject", "body", "action_url"))
        url = html.escape(str(login_url or payload["action_url"]))
        button_label = "Passwort festlegen" if payload.get("event_type") == "password.reset" else "In FamilienPlan öffnen"
        decision_html = ""
        if payload.get("event_type") in {"notification.digest", "notification.resend"}:
            parts = []
            decision_entries = [entry for entry in payload.get("entries", []) if entry.get("decision_actions")]
            for entry in decision_entries:
                entry_subject = html.escape(str(entry.get("subject", "Anfrage")))
                entry_body = html.escape(str(entry.get("body", "")))
                buttons = []
                for action in entry.get("decision_actions", []):
                    if action.get("label"):
                        buttons.append(f'<span style="display:block;font-weight:bold;margin:10px 0 2px">{html.escape(str(action["label"]))}</span>')
                    buttons.append(f'<a href="{html.escape(action["approve_url"], quote=True)}" style="display:inline-block;background:#3b8f63;color:white;text-decoration:none;font-weight:bold;padding:10px 13px;border-radius:8px;margin:4px 5px 4px 0">Bestätigen</a>')
                    buttons.append(f'<a href="{html.escape(action["reject_url"], quote=True)}" style="display:inline-block;background:#a6463a;color:white;text-decoration:none;font-weight:bold;padding:10px 13px;border-radius:8px;margin:4px 5px 4px 0">Ablehnen</a>')
                parts.append(f'<div style="border-top:1px solid #dfe5e0;margin-top:24px;padding-top:20px"><h2 style="font-size:18px;margin:0 0 8px">{entry_subject}</h2><p style="line-height:1.6;white-space:pre-line;margin:0">{entry_body}</p>{"<p style=\"margin:14px 0 0\">" + "".join(buttons) + "</p>" if buttons else ""}</div>')
            batch_buttons = []
            for action in payload.get("decision_batch_actions", []):
                color = "#3b8f63" if action["label"] == "Alle bestätigen" else "#a6463a"
                batch_buttons.append(f'<a href="{html.escape(action["url"], quote=True)}" style="display:inline-block;background:{color};color:white;text-decoration:none;font-weight:bold;padding:11px 15px;border-radius:8px;margin:4px 5px 4px 0">{html.escape(action["label"])}</a>')
            if batch_buttons:
                parts.append(f'<div style="border-top:2px solid #23332e;margin-top:28px;padding-top:20px"><h2 style="font-size:18px;margin:0 0 8px">Gesamte Anfrage-Mail</h2><p style="line-height:1.6;margin:0 0 8px">Alle noch offenen Anfragen aus dieser Mail gemeinsam entscheiden:</p><p style="margin:0">{"".join(batch_buttons)}</p></div>')
            decision_html = "".join(parts)
        body_html = "" if decision_html else f'<p style="line-height:1.6;white-space:pre-line">{html.escape(str(payload["body"]))}</p>'
        calendar_html = ""
        if calendar_links:
            calendar_items = "".join(
                f'<li style="margin:7px 0"><a href="{html.escape(str(item.get("url", "")), quote=True)}" style="color:#267cb5">{html.escape(str(item.get("name", "Kalender")))}</a></li>'
                for item in calendar_links
            )
            calendar_html = f'<div style="border-top:1px solid #dfe5e0;margin-top:28px;padding-top:20px"><h2 style="font-size:18px;margin:0 0 8px">Kalender abonnieren</h2><p style="line-height:1.6;margin:0 0 8px">Diese Kalender sind für dich freigegeben:</p><ul style="line-height:1.5;padding-left:20px;margin:0">{calendar_items}</ul></div>'
        login_hint_html = (
            '<p style="margin:10px 0 0;color:#708079;font-size:12px">'
            'Dieser Link ist 14 Tage ab Versand gültig und kann in dieser Zeit mehrfach ohne Passwort verwendet werden.'
            '</p>'
            if login_url else ""
        )
        message.add_alternative(f'''<!doctype html><html><body style="margin:0;background:#f5f6f2;font-family:Arial,sans-serif;color:#23332e"><div style="max-width:600px;margin:30px auto;background:white;border:1px solid #dfe5e0;border-radius:14px;padding:32px"><h1 style="font-family:Georgia,serif;font-size:28px">{subject}</h1>{body_html}{decision_html}<p style="margin-top:28px"><a href="{url}" style="display:inline-block;background:#3ba4e5;color:white;text-decoration:none;font-weight:bold;padding:13px 18px;border-radius:9px">{button_label}</a></p>{login_hint_html}<p style="margin-top:24px;color:#708079;font-size:12px">Falls ein Button nicht funktioniert, öffne FamilienPlan direkt:<br>{action_url}</p>{calendar_html}</div></body></html>''', subtype="html")
    smtp_class = smtplib.SMTP_SSL if config.get("security") == "ssl" else smtplib.SMTP
    with smtp_class(config["host"], config["port"], timeout=15) as smtp:
        if config.get("security") == "starttls":
            smtp.starttls()
        if config["username"]:
            smtp.login(config["username"], config["password"] or "")
        smtp.send_message(message)


async def deliver_outbox_once():
    with SessionLocal() as db:
        due = list(db.scalars(select(OutboxMessage).where(
            OutboxMessage.channel.in_(["email", "push"]),
            OutboxMessage.delivered_at.is_(None), OutboxMessage.available_at <= utcnow(),
            OutboxMessage.attempts < 8).order_by(OutboxMessage.id).limit(20).with_for_update(skip_locked=True)))
        config = mail_config(db)
        for item in due:
            try:
                if item.channel == "push":
                    from app.push import deliver_push
                    import asyncio
                    await asyncio.to_thread(deliver_push, db, item, get_settings().app_origin)
                    continue
                if not config["host"]:
                    raise RuntimeError("Kein SMTP-Server konfiguriert")
                import asyncio
                await asyncio.to_thread(_send_mail, config, item.recipient_key, item.payload)
                item.delivered_at = utcnow()
                item.last_error = None
            except Exception as exc:
                item.attempts += 1
                item.last_error = str(exc)[:1000]
                item.available_at = utcnow() + timedelta(seconds=min(3600, 15 * (2 ** item.attempts)))
        db.commit()
