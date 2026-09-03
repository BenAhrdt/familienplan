from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.api.dependencies import admin, current_user, require_csrf
from app.core.database import get_db
from app.core.security import new_token, token_hash, utcnow
from app.integrations import mail_config, queue_mail
from app.models.entities import ApiToken, ApplicationSetting, Birthday, CalendarEvent, Child, ChildUserPermission, OutboxMessage, PlanStatus, Role, Stay, User

router = APIRouter()
ALL_SCOPES = ["read:children", "read:stays", "read:appointments", "read:birthdays", "read:holidays", "read:private"]


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    scopes: list[str] = ALL_SCOPES[:-1]
    child_ids: list[int] = []
    user_id: int


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
    permitted = (set(db.scalars(select(Child.id).where(Child.is_active.is_(True)))) if user.role == Role.ADMIN
                 else set(db.scalars(select(ChildUserPermission.child_id).where(ChildUserPermission.user_id == user.id))))
    return permitted & explicit if explicit else permitted


def visible_custom_labels(db: Session, user: User) -> set[str]:
    row = db.get(ApplicationSetting, "custom_calendar_types")
    if user.role == Role.ADMIN:
        return {item["name"] for item in (row.value or [])} if row else set()
    return {item["name"] for item in (row.value or []) if user.id in item.get("visible_to_user_ids", []) or user.id in item.get("editable_by_user_ids", [])} if row else set()


def need(token, scope):
    if scope not in token.scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"API-Schlüssel benötigt {scope}")


@router.get("/integration-tokens")
def tokens(db: Session = Depends(get_db), _: User = Depends(admin)):
    rows = list(db.scalars(select(ApiToken).order_by(ApiToken.id.desc())))
    users = {item.id:item for item in db.scalars(select(User).where(User.id.in_({row.user_id for row in rows})))}
    return [{"id": x.id, "name": x.name, "scopes": x.scopes, "last_used_at": x.last_used_at, "revoked_at": x.revoked_at,
             "user_id":x.user_id,"user_name":users[x.user_id].display_name if x.user_id in users else "Unbekannt"} for x in rows]


@router.post("/integration-tokens", status_code=201, dependencies=[Depends(require_csrf)])
def create_token(data: TokenCreate, db: Session = Depends(get_db), user: User = Depends(admin)):
    invalid = set(data.scopes) - set(ALL_SCOPES)
    if invalid: raise HTTPException(422, f"Unbekannte Rechte: {', '.join(sorted(invalid))}")
    owner = db.get(User, data.user_id)
    if not owner or not owner.is_active or owner.is_pending: raise HTTPException(422, "Aktive Person auswählen")
    raw = new_token()
    row = ApiToken(user_id=owner.id, name=data.name, token_hash=token_hash(raw), scopes=data.scopes + [f"child:{x}" for x in data.child_ids])
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "token": raw, "scopes": row.scopes}


@router.get("/people/{user_id}/api-token")
def person_api_token(user_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    person = db.get(User, user_id)
    if not person or not person.is_active: raise HTTPException(404, "Person nicht gefunden")
    row = db.scalar(select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None)).order_by(ApiToken.id.desc()))
    return {"active": bool(row), "id": row.id if row else None, "last_used_at": row.last_used_at if row else None}


@router.post("/people/{user_id}/api-token", status_code=201, dependencies=[Depends(require_csrf)])
def create_person_api_token(user_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    person = db.get(User, user_id)
    if not person or not person.is_active or person.is_pending: raise HTTPException(404, "Aktive Person nicht gefunden")
    now = utcnow()
    for old in db.scalars(select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))): old.revoked_at = now
    raw = new_token()
    row = ApiToken(user_id=user_id, name=f"API · {person.display_name}", token_hash=token_hash(raw), scopes=ALL_SCOPES)
    db.add(row); db.commit(); db.refresh(row)
    return {"active": True, "id": row.id, "token": raw, "last_used_at": None}


@router.delete("/people/{user_id}/api-token", status_code=204, dependencies=[Depends(require_csrf)])
def revoke_person_api_token(user_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    for row in db.scalars(select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))): row.revoked_at = utcnow()
    db.commit()


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
            CalendarEvent.starts_at < to_at, CalendarEvent.ends_at > from_at,
            (CalendarEvent.event_type != "PRIVATE")
            | (CalendarEvent.created_by_id == user.id)
            | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]))
        if "read:private" not in token.scopes: query = query.where(CalendarEvent.is_private.is_(False))
        if user.role != Role.ADMIN:
            custom_labels = visible_custom_labels(db, user)
            query = query.where(or_(CalendarEvent.event_type.in_(user.allowed_event_types or []),
                                    CalendarEvent.event_type == "PRIVATE",
                                    and_(CalendarEvent.event_type == "OTHER", CalendarEvent.custom_type_label.in_(custom_labels))))
            query = query.where((CalendarEvent.is_private.is_(False)) | (CalendarEvent.created_by_id == user.id) | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]))
        for x in db.scalars(query.order_by(CalendarEvent.starts_at)):
            kind = "school_holiday" if x.category == "HOLIDAY" else "school_event" if x.category == "SCHOOL" else "appointment"
            if kind == "school_holiday" and "read:holidays" not in token.scopes: continue
            if kind != "school_holiday" and "read:appointments" not in token.scopes: continue
            result.append({"type":kind,"event_type":x.event_type,"custom_type_label":x.custom_type_label,"id":x.id,"child_id":x.child_id,"title":x.title,"starts_at":x.starts_at,"ends_at":x.ends_at,"all_day":x.all_day})
    if "read:birthdays" in token.scopes:
        for x in db.scalars(select(Birthday)):
            if user.role != Role.ADMIN and "BIRTHDAY" not in (user.allowed_event_types or []): continue
            if x.is_private and ("read:private" not in token.scopes or (x.created_by_id != user.id and user.id not in (x.visible_to_user_ids or []))): continue
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


@router.get("/outbox")
def outbox(db: Session = Depends(get_db), _: User = Depends(admin)):
    return [{"id":x.id,"channel":x.channel,"recipient":x.recipient_key,"event_type":x.event_type,"attempts":x.attempts,"last_error":x.last_error,
             "delivered_at":x.delivered_at,"created_at":x.created_at} for x in db.scalars(select(OutboxMessage).order_by(OutboxMessage.id.desc()).limit(100))]
