from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import admin, current_user, require_csrf
from app.core.database import get_db
from app.core.security import new_token, token_hash, utcnow
from app.integrations import mail_config, queue_mail, queue_webhooks
from app.models.entities import ApiToken, ApplicationSetting, Birthday, CalendarEvent, Child, ChildUserPermission, OutboxMessage, PlanStatus, Role, Stay, User, WebhookEndpoint

router = APIRouter()
ALL_SCOPES = ["read:children", "read:stays", "read:appointments", "read:birthdays", "read:holidays", "read:private"]


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    scopes: list[str] = ALL_SCOPES[:-1]
    child_ids: list[int] = []


class HookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    url: str
    events: list[str] = ["*"]
    is_active: bool = True
    secret: str | None = None


class MailConfig(BaseModel):
    enabled: bool = False
    host: str | None = None
    port: int = 587
    username: str | None = None
    password: str | None = None
    from_address: str = "FamilienPlan <familienplan@example.de>"
    app_url: str | None = None
    security: str = Field(default="starttls", pattern=r"^(starttls|ssl|none)$")


def api_context(request: Request, db: Session = Depends(get_db)):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API-Schlüssel erforderlich")
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash(auth[7:]), ApiToken.revoked_at.is_(None)))
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiger API-Schlüssel")
    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API-Schlüssel ist nicht aktiv")
    token.last_used_at = utcnow(); db.commit()
    return token, user


def allowed_children(token, user, db):
    explicit = {int(scope.split(":", 1)[1]) for scope in token.scopes if scope.startswith("child:")}
    if explicit:
        return explicit
    if user.role == Role.ADMIN:
        return set(db.scalars(select(Child.id).where(Child.is_active.is_(True))))
    return set(db.scalars(select(ChildUserPermission.child_id).where(ChildUserPermission.user_id == user.id)))


def need(token, scope):
    if scope not in token.scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"API-Schlüssel benötigt {scope}")


@router.get("/integration-tokens")
def tokens(db: Session = Depends(get_db), _: User = Depends(admin)):
    return [{"id": x.id, "name": x.name, "scopes": x.scopes, "last_used_at": x.last_used_at, "revoked_at": x.revoked_at}
            for x in db.scalars(select(ApiToken).order_by(ApiToken.id.desc()))]


@router.post("/integration-tokens", status_code=201, dependencies=[Depends(require_csrf)])
def create_token(data: TokenCreate, db: Session = Depends(get_db), user: User = Depends(admin)):
    invalid = set(data.scopes) - set(ALL_SCOPES)
    if invalid: raise HTTPException(422, f"Unbekannte Rechte: {', '.join(sorted(invalid))}")
    raw = new_token()
    row = ApiToken(user_id=user.id, name=data.name, token_hash=token_hash(raw), scopes=data.scopes + [f"child:{x}" for x in data.child_ids])
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "token": raw, "scopes": row.scopes}


@router.delete("/integration-tokens/{token_id}", status_code=204, dependencies=[Depends(require_csrf)])
def revoke_token(token_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    row = db.get(ApiToken, token_id)
    if not row: raise HTTPException(404, "API-Schlüssel nicht gefunden")
    row.revoked_at = utcnow(); db.commit()


@router.get("/integrations/v1/status")
def integration_status(context=Depends(api_context)):
    token, _ = context
    return {"api_version": "v1", "status": "ok", "server_time": utcnow(), "scopes": token.scopes}


@router.get("/integrations/v1/children")
def integration_children(context=Depends(api_context), db: Session = Depends(get_db)):
    token, user = context; need(token, "read:children")
    ids = allowed_children(token, user, db)
    return [{"type": "child", "id": x.id, "name": x.display_name, "default_responsible_user_id": x.default_responsible_user_id}
            for x in db.scalars(select(Child).where(Child.id.in_(ids)).order_by(Child.display_name))]


@router.get("/integrations/v1/events", include_in_schema=False)
@router.get("/integrations/v1/calendar")
def integration_events(from_at: datetime, to_at: datetime, child_id: int | None = None,
                       context=Depends(api_context), db: Session = Depends(get_db)):
    if to_at <= from_at or to_at - from_at > timedelta(days=366):
        raise HTTPException(422, "Zeitraum muss positiv und höchstens 366 Tage lang sein")
    token, user = context; ids = allowed_children(token, user, db)
    if child_id is not None:
        if child_id not in ids: raise HTTPException(403, "Kein Zugriff auf dieses Kind")
        ids = {child_id}
    result = []
    if "read:stays" in token.scopes:
        rows = db.scalars(select(Stay).where(Stay.child_id.in_(ids), Stay.status == PlanStatus.CONFIRMED,
            Stay.starts_at < to_at, Stay.ends_at > from_at).order_by(Stay.starts_at))
        for x in rows:
            result.append({"type":"stay","id":x.id,"child_id":x.child_id,"responsible_user_id":x.responsible_user_id,
                           "starts_at":x.starts_at,"ends_at":x.ends_at,"title":x.note})
    if "read:appointments" in token.scopes or "read:holidays" in token.scopes:
        query = select(CalendarEvent).where(or_(CalendarEvent.child_id.is_(None), CalendarEvent.child_id.in_(ids)),
            CalendarEvent.starts_at < to_at, CalendarEvent.ends_at > from_at)
        if "read:private" not in token.scopes: query = query.where(CalendarEvent.is_private.is_(False))
        for x in db.scalars(query.order_by(CalendarEvent.starts_at)):
            kind = "school_holiday" if x.category == "HOLIDAY" else "school_event" if x.category == "SCHOOL" else "appointment"
            if kind == "school_holiday" and "read:holidays" not in token.scopes: continue
            if kind != "school_holiday" and "read:appointments" not in token.scopes: continue
            result.append({"type":kind,"id":x.id,"child_id":x.child_id,"title":x.title,"starts_at":x.starts_at,"ends_at":x.ends_at,"all_day":x.all_day})
    if "read:birthdays" in token.scopes:
        for x in db.scalars(select(Birthday)):
            if x.is_private and "read:private" not in token.scopes: continue
            for year in range(from_at.year, to_at.year + 1):
                try: occurrence = x.birth_date.replace(year=year)
                except ValueError: occurrence = x.birth_date.replace(year=year, day=28)
                start = datetime.combine(occurrence, datetime.min.time(), tzinfo=from_at.tzinfo)
                if from_at <= start < to_at:
                    result.append({"type":"birthday","id":x.id,"title":x.display_name,"starts_at":start,
                                   "ends_at":start+timedelta(days=1),"age":year-x.birth_date.year})
    return sorted(result, key=lambda x: x["starts_at"])


@router.get("/integrations/v1/children/{child_id}/location")
def child_location(child_id: int, at: datetime | None = None, context=Depends(api_context), db: Session = Depends(get_db)):
    token, user = context; need(token, "read:stays")
    if child_id not in allowed_children(token, user, db): raise HTTPException(403, "Kein Zugriff auf dieses Kind")
    at = at or utcnow(); child = db.get(Child, child_id)
    stay = db.scalar(select(Stay).where(Stay.child_id == child_id, Stay.status == PlanStatus.CONFIRMED,
        Stay.starts_at <= at, Stay.ends_at > at).order_by(Stay.updated_at.desc()))
    person_id = stay.responsible_user_id if stay else child.default_responsible_user_id
    person = db.get(User, person_id) if person_id else None
    next_row = db.scalar(select(Stay).where(Stay.child_id == child_id, Stay.status == PlanStatus.CONFIRMED,
        Stay.starts_at > at).order_by(Stay.starts_at))
    return {"type":"location_state","child_id":child_id,"at":at,"responsible_user_id":person_id,
            "responsible_name":person.display_name if person else None,"source":"stay" if stay else "default",
            "current_until":stay.ends_at if stay else None,"next_change_at":next_row.starts_at if next_row else None}


@router.get("/settings/mail")
def get_mail(db: Session = Depends(get_db), _: User = Depends(admin)):
    value = mail_config(db); value.pop("password", None)
    row = db.get(ApplicationSetting, "mail")
    value["password_configured"] = bool((row.value or {}).get("password") if row else False) or bool(mail_config(db).get("password"))
    return value


@router.put("/settings/mail", dependencies=[Depends(require_csrf)])
def save_mail(data: MailConfig, db: Session = Depends(get_db), _: User = Depends(admin)):
    old = db.get(ApplicationSetting, "mail"); value = data.model_dump()
    if not data.password and old: value["password"] = (old.value or {}).get("password")
    if old: old.value = value
    else: db.add(ApplicationSetting(key="mail", value=value))
    db.commit(); safe = dict(value); safe.pop("password", None); safe["password_configured"] = bool(value.get("password")); return safe


@router.post("/settings/mail/test", dependencies=[Depends(require_csrf)])
def test_mail(db: Session = Depends(get_db), user: User = Depends(admin)):
    config = mail_config(db)
    if not config.get("enabled") or not config.get("host"):
        raise HTTPException(422, "Bitte aktiviere und speichere zuerst einen SMTP-Server")
    queue_mail(db, user.id, f"mail-test:{utcnow().timestamp()}", "mail.test", "FamilienPlan Testnachricht", "Der E-Mail-Versand von FamilienPlan ist eingerichtet.")
    db.commit(); return {"queued": True, "recipient": user.email}


@router.get("/webhooks")
def webhooks(db: Session = Depends(get_db), _: User = Depends(admin)):
    return [{"id":x.id,"name":x.name,"url":x.url,"events":x.events,"is_active":x.is_active,"created_at":x.created_at}
            for x in db.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.name))]


@router.post("/webhooks", status_code=201, dependencies=[Depends(require_csrf)])
def create_hook(data: HookCreate, db: Session = Depends(get_db), user: User = Depends(admin)):
    parsed = urlparse(data.url)
    if parsed.scheme not in {"http","https"} or not parsed.netloc: raise HTTPException(422, "Nur vollständige HTTP- oder HTTPS-Adressen sind erlaubt")
    secret = data.secret or new_token()
    row = WebhookEndpoint(name=data.name,url=data.url,secret=secret,events=data.events,is_active=data.is_active,created_by_id=user.id)
    db.add(row); db.commit(); db.refresh(row)
    return {"id":row.id,"name":row.name,"url":row.url,"events":row.events,"is_active":row.is_active,"secret":secret}


@router.delete("/webhooks/{hook_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_hook(hook_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    row=db.get(WebhookEndpoint,hook_id)
    if not row: raise HTTPException(404,"Webhook nicht gefunden")
    db.delete(row); db.commit()


@router.post("/webhooks/{hook_id}/test", dependencies=[Depends(require_csrf)])
def test_hook(hook_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    if not db.get(WebhookEndpoint,hook_id): raise HTTPException(404,"Webhook nicht gefunden")
    queue_webhooks(db,f"webhook-test:{hook_id}:{utcnow().timestamp()}","system.test",{"message":"FamilienPlan Webhook funktioniert"})
    db.commit(); return {"queued":True}


@router.get("/outbox")
def outbox(db: Session = Depends(get_db), _: User = Depends(admin)):
    return [{"id":x.id,"channel":x.channel,"recipient":x.recipient_key,"event_type":x.event_type,"attempts":x.attempts,"last_error":x.last_error,
             "delivered_at":x.delivered_at,"created_at":x.created_at} for x in db.scalars(select(OutboxMessage).order_by(OutboxMessage.id.desc()).limit(100))]
