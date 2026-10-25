import hashlib
import logging
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
import hmac
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
import httpx
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.api.dependencies import admin, current_user, require_csrf
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import new_token, token_hash, utcnow
from app.integrations import default_calendar_feed_event_types, ensure_default_calendar_feeds, mail_config, queue_mail
from app.models.entities import ApiToken, ApplicationSetting, Birthday, CalendarEvent, CalendarFeed, Child, ChildUserPermission, OutboxMessage, PlanStatus, Role, Stay, User

router = APIRouter()
settings = get_settings()
logger = logging.getLogger("familienplan.calendar-feed")
calendar_feed_fallback_tokens = URLSafeSerializer(settings.secret_key, salt="familienplan-calendar-feed")
ALL_SCOPES = ["read:children", "read:stays", "read:appointments", "read:birthdays", "read:holidays", "read:private"]
CALENDAR_FEED_EVENT_TYPES = ["STAY", "GENERAL", "SCHOOL", "SCHOOL_HOLIDAY", "WASTE", "BIRTHDAY", "CLEANING", "PRIVATE", "OTHER"]
CALENDAR_FEED_STAY_VISIBILITY = ["OWN", "STANDARD", "OTHER"]


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    scopes: list[str] = ALL_SCOPES[:-1]
    child_ids: list[int] = []
    user_id: int


class PersonTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class CalendarFeedCreate(BaseModel):
    name: str = Field(default="Mein FamilienPlan-Kalender", min_length=1, max_length=160)
    event_types: list[str] = Field(default_factory=list)
    stay_visibility: list[str] = Field(default_factory=lambda: ["OWN"])

    @field_validator("stay_visibility")
    @classmethod
    def valid_stay_visibility(cls, value: list[str]) -> list[str]:
        invalid = set(value) - set(CALENDAR_FEED_STAY_VISIBILITY)
        if invalid:
            raise ValueError("Unbekannte Betreuungsauswahl")
        return list(dict.fromkeys(value))


class CalendarFeedUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    event_types: list[str] = Field(default_factory=list)
    stay_visibility: list[str] = Field(default_factory=lambda: ["OWN"])

    @field_validator("stay_visibility")
    @classmethod
    def valid_stay_visibility(cls, value: list[str]) -> list[str]:
        invalid = set(value) - set(CALENDAR_FEED_STAY_VISIBILITY)
        if invalid:
            raise ValueError("Unbekannte Betreuungsauswahl")
        return list(dict.fromkeys(value))


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
    raw = auth[7:].strip()
    token = None
    if raw.startswith("fp_"):
        try:
            token_id = int(raw.split("_", 2)[1])
        except (IndexError, ValueError):
            token_id = None
        if token_id is not None:
            candidate = db.get(ApiToken, token_id)
            if candidate and candidate.revoked_at is None and hmac.compare_digest(candidate.token_hash, token_hash(raw)):
                token = candidate
    else:
        token = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash(raw), ApiToken.revoked_at.is_(None)))
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
    secret = new_token()
    row = ApiToken(user_id=owner.id, name=data.name, token_hash=token_hash(secret), scopes=data.scopes + [f"child:{x}" for x in data.child_ids])
    db.add(row); db.flush()
    raw = f"fp_{row.id}_{secret}"
    row.token_hash = token_hash(raw)
    db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "token": raw, "scopes": row.scopes}


@router.get("/people/{user_id}/api-tokens")
def person_api_tokens(user_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    person = db.get(User, user_id)
    if not person or not person.is_active: raise HTTPException(404, "Person nicht gefunden")
    rows = db.scalars(select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None)).order_by(ApiToken.name, ApiToken.id))
    return [{"id":row.id,"name":row.name,"last_used_at":row.last_used_at} for row in rows]


@router.post("/people/{user_id}/api-tokens", status_code=201, dependencies=[Depends(require_csrf)])
def create_person_api_token(user_id: int, data: PersonTokenCreate, db: Session = Depends(get_db), _: User = Depends(admin)):
    person = db.get(User, user_id)
    if not person or not person.is_active or person.is_pending: raise HTTPException(404, "Aktive Person nicht gefunden")
    secret = new_token()
    row = ApiToken(user_id=user_id, name=data.name.strip(), token_hash=token_hash(secret), scopes=ALL_SCOPES)
    db.add(row); db.flush()
    raw = f"fp_{row.id}_{secret}"
    row.token_hash = token_hash(raw)
    db.commit(); db.refresh(row)
    return {"id": row.id, "name":row.name, "token": raw, "last_used_at": None}


@router.delete("/people/{user_id}/api-tokens/{token_id}", status_code=204, dependencies=[Depends(require_csrf)])
def revoke_person_api_token(user_id: int, token_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    row = db.scalar(select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None)))
    if not row: raise HTTPException(404, "API-Schlüssel nicht gefunden")
    row.revoked_at = utcnow()
    db.commit()


@router.delete("/integration-tokens/{token_id}", status_code=204, dependencies=[Depends(require_csrf)])
def revoke_token(token_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    row = db.get(ApiToken, token_id)
    if not row: raise HTTPException(404, "API-Schlüssel nicht gefunden")
    row.revoked_at = utcnow(); db.commit()


@router.get("/calendar-feeds")
def calendar_feeds(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_default_calendar_feeds(db, user)
    db.commit()
    rows = db.scalars(select(CalendarFeed).where(CalendarFeed.user_id == user.id).order_by(CalendarFeed.id.desc()))
    return {"feeds": [{"id": row.id, "name": row.name, "event_types": row.event_types or CALENDAR_FEED_EVENT_TYPES,
                        "stay_visibility": row.stay_visibility if row.stay_visibility is not None else ["OWN"],
                        "created_at": row.created_at, "last_used_at": row.last_used_at,
                        "revoked_at": row.revoked_at, "url": calendar_feed_url(row)} for row in rows],
            "available_event_types": available_calendar_feed_event_types(user)}


def calendar_feed_token(row: CalendarFeed) -> str:
    return row.token_value or calendar_feed_fallback_tokens.dumps({"feed_id": row.id})


def calendar_feed_url(row: CalendarFeed) -> str:
    return f"{settings.app_origin.rstrip('/')}/api/v1/calendar-feeds/{calendar_feed_token(row)}.ics"


def available_calendar_feed_event_types(user: User) -> list[str]:
    return default_calendar_feed_event_types(user)


@router.post("/calendar-feeds", status_code=201, dependencies=[Depends(require_csrf)])
def create_calendar_feed(data: CalendarFeedCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    name = data.name.strip()
    if not name:
        raise HTTPException(422, "Bitte gib einen Namen für den Kalenderfeed ein")
    available = set(available_calendar_feed_event_types(user))
    selected = set(data.event_types) or available
    invalid = selected - set(CALENDAR_FEED_EVENT_TYPES)
    if invalid or not selected.issubset(available):
        raise HTTPException(422, "Der Kalenderfeed darf nur sichtbare Kategorien enthalten")
    if set(data.stay_visibility) - set(CALENDAR_FEED_STAY_VISIBILITY):
        raise HTTPException(422, "Die Betreuungsauswahl ist ungültig")
    secret = new_token()
    row = CalendarFeed(user_id=user.id, name=name, event_types=sorted(selected), stay_visibility=data.stay_visibility,
                       token_hash=token_hash(secret), token_value=secret)
    db.add(row)
    db.commit()
    db.refresh(row)
    url = calendar_feed_url(row)
    return {"id": row.id, "name": row.name, "event_types": row.event_types,
            "stay_visibility": row.stay_visibility if row.stay_visibility is not None else ["OWN"], "created_at": row.created_at,
            "last_used_at": row.last_used_at, "url": url}


@router.put("/calendar-feeds/{feed_id}", dependencies=[Depends(require_csrf)])
def update_calendar_feed(feed_id: int, data: CalendarFeedUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.scalar(select(CalendarFeed).where(CalendarFeed.id == feed_id, CalendarFeed.user_id == user.id))
    if not row or row.revoked_at is not None:
        raise HTTPException(404, "Kalenderfeed nicht gefunden")
    name = data.name.strip()
    if not name:
        raise HTTPException(422, "Bitte gib einen Namen für den Kalenderfeed ein")
    available = set(available_calendar_feed_event_types(user))
    selected = set(data.event_types) or available
    invalid = selected - set(CALENDAR_FEED_EVENT_TYPES)
    if invalid or not selected.issubset(available):
        raise HTTPException(422, "Der Kalenderfeed darf nur sichtbare Kategorien enthalten")
    if set(data.stay_visibility) - set(CALENDAR_FEED_STAY_VISIBILITY):
        raise HTTPException(422, "Die Betreuungsauswahl ist ungültig")
    row.name = name
    row.event_types = sorted(selected)
    row.stay_visibility = data.stay_visibility
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "event_types": row.event_types,
            "stay_visibility": row.stay_visibility if row.stay_visibility is not None else ["OWN"], "created_at": row.created_at,
            "last_used_at": row.last_used_at, "url": calendar_feed_url(row)}


@router.delete("/calendar-feeds/{feed_id}", status_code=204, dependencies=[Depends(require_csrf)])
def revoke_calendar_feed(feed_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.scalar(select(CalendarFeed).where(CalendarFeed.id == feed_id, CalendarFeed.user_id == user.id))
    if not row or row.revoked_at is not None:
        raise HTTPException(404, "Kalenderfeed nicht gefunden")
    row.revoked_at = utcnow()
    db.commit()


def _ics_escape(value: object) -> str:
    return (str(value or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n")
            .replace("\r", "\\n"))


def _fold_ics_line(line: str) -> str:
    chunks: list[str] = []
    current = ""
    limit = 75
    for character in line:
        if current and len((current + character).encode("utf-8")) > limit:
            chunks.append(current)
            current = " " + character
            limit = 74
        else:
            current += character
    chunks.append(current)
    return "\r\n".join(chunks)


def _ics_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ics_date(value: datetime) -> str:
    # VALUE=DATE represents a calendar date, not an instant in UTC. Converting
    # a local midnight in Europe/Berlin to UTC would shift it to the previous
    # day in the exported calendar. Persisted all-day events may already have
    # been converted to UTC by PostgreSQL, so convert aware values back to the
    # application timezone before extracting the date.
    if value.tzinfo is not None:
        value = value.astimezone(ZoneInfo(settings.app_timezone))
    return value.date().strftime("%Y%m%d")


def calendar_feed_ics(events: list[dict], feed_name: str) -> str:
    now = utcnow()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FamilienPlan//Familienkalender//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(feed_name)}",
    ]
    for event in events:
        identity = "|".join(str(event.get(key, "")) for key in ("source", "event_type", "id", "child_id", "starts_at", "ends_at"))
        uid = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32] + "@familienplan"
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{_ics_datetime(now)}"])
        starts_at = event["starts_at"]
        ends_at = event["ends_at"]
        if event.get("all_day"):
            lines.extend([f"DTSTART;VALUE=DATE:{_ics_date(starts_at)}", f"DTEND;VALUE=DATE:{_ics_date(ends_at)}"])
        else:
            lines.extend([f"DTSTART:{_ics_datetime(starts_at)}", f"DTEND:{_ics_datetime(ends_at)}"])
        lines.append(f"SUMMARY:{_ics_escape(event.get('title') or 'FamilienPlan')}")
        if event.get("description"):
            lines.append(f"DESCRIPTION:{_ics_escape(event['description'])}")
        if event.get("event_type"):
            lines.append(f"CATEGORIES:{_ics_escape(event['event_type'])}")
        lines.extend([f"X-FAMILIENPLAN-EVENT-TYPE:{_ics_escape(event.get('event_type'))}", "END:VEVENT"])
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n"


def filter_calendar_feed_events(events: list[dict], event_types: list[str] | None) -> list[dict]:
    selected = set(event_types or CALENDAR_FEED_EVENT_TYPES)
    return [event for event in events if event.get("event_type") in selected]


def _fetch_school_holiday_rows(state: str, year: int) -> list[dict]:
    response = httpx.get(
        "https://openholidaysapi.org/SchoolHolidays",
        params={
            "countryIsoCode": "DE",
            "subdivisionCode": f"DE-{state}",
            "languageIsoCode": "DE",
            "validFrom": f"{year}-01-01",
            "validTo": f"{year}-12-31",
        },
        timeout=10,
        headers={"User-Agent": "FamilienPlan/1.0", "Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def school_holiday_events(from_at: datetime, to_at: datetime, child_ids: set[int], db: Session) -> list[dict]:
    """Return the automatically generated school holidays for the feed's visible children."""
    if not child_ids:
        return []

    states = {
        (child.school_state_code or "").strip().upper()
        for child in db.scalars(select(Child).where(Child.id.in_(child_ids), Child.is_active.is_(True)))
        if (child.school_state_code or "").strip()
    }
    if not states:
        return []

    timezone = ZoneInfo(settings.app_timezone)
    local_from = from_at.astimezone(timezone) if from_at.tzinfo else from_at.replace(tzinfo=timezone)
    local_to = to_at.astimezone(timezone) if to_at.tzinfo else to_at.replace(tzinfo=timezone)
    years = range(local_from.year, local_to.year + 1)
    result: list[dict] = []

    for state in sorted(states):
        for year in years:
            try:
                rows = _fetch_school_holiday_rows(state, year)
            except (httpx.HTTPError, ValueError, TypeError):
                logger.warning("Schulferien konnten für %s/%s nicht geladen werden", state, year, exc_info=True)
                continue
            for row in rows:
                try:
                    starts_on = date.fromisoformat(str(row["startDate"]))
                    ends_on = date.fromisoformat(str(row["endDate"]))
                    names = row.get("name") or []
                    title = next((item["text"] for item in names if item.get("language") == "DE"), None)
                    title = title or (names[0].get("text") if names else None) or "Schulferien"
                except (KeyError, TypeError, ValueError):
                    continue

                starts_at = datetime.combine(starts_on, time.min, tzinfo=timezone)
                ends_at = datetime.combine(ends_on + timedelta(days=1), time.min, tzinfo=timezone)
                if starts_at >= local_to or ends_at <= local_from:
                    continue
                result.append({
                    "source": f"school-holiday:{state}",
                    "event_type": "SCHOOL_HOLIDAY",
                    "id": f"{state}:{starts_on.isoformat()}:{ends_on.isoformat()}:{title}",
                    "child_id": None,
                    "title": title,
                    "description": None,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "all_day": True,
                })
    return result


def calendar_feed_events(row: CalendarFeed, user: User, start: datetime, end: datetime, db: Session) -> list[dict]:
    event_types = row.event_types or CALENDAR_FEED_EVENT_TYPES
    stay_visibility = set(row.stay_visibility if row.stay_visibility is not None else ["OWN"])
    context = (SimpleNamespace(scopes=ALL_SCOPES), user)
    # A care feed defaults to the periods in which the child is with the feed
    # owner. Standard care and care by other people can be opted in per feed.
    events = integration_events(start, end, context=context, db=db)
    stay_child_ids = {
        event["child_id"] for event in events
        if event.get("event_type") == "STAY" and event.get("child_id") is not None
    }
    default_responsible_by_child = {
        child.id: child.default_responsible_user_id
        for child in db.scalars(select(Child).where(Child.id.in_(stay_child_ids)))
    } if stay_child_ids else {}
    def stay_visibility_for(event: dict) -> set[str]:
        responsible_id = event.get("responsible_user_id")
        default_id = default_responsible_by_child.get(event.get("child_id"))
        visibility: set[str] = set()
        if responsible_id == user.id:
            visibility.add("OWN")
        if responsible_id == default_id:
            visibility.add("STANDARD")
        if responsible_id != user.id and responsible_id != default_id:
            visibility.add("OTHER")
        return visibility

    events = [
        event for event in events
        if event.get("event_type") != "STAY"
        or stay_visibility_for(event) & stay_visibility
    ]
    if "SCHOOL_HOLIDAY" in event_types:
        events.extend(school_holiday_events(start, end, allowed_children(context[0], user, db), db))
    return filter_calendar_feed_events(events, event_types)


@router.get("/calendar-feeds/{token}.ics", include_in_schema=False)
def calendar_feed(token: str, db: Session = Depends(get_db)):
    row = db.scalar(select(CalendarFeed).where(CalendarFeed.token_hash == token_hash(token), CalendarFeed.revoked_at.is_(None)))
    if not row:
        try:
            payload = calendar_feed_fallback_tokens.loads(token)
            feed_id = payload.get("feed_id") if isinstance(payload, dict) else None
        except BadSignature:
            feed_id = None
        if isinstance(feed_id, int):
            row = db.scalar(select(CalendarFeed).where(CalendarFeed.id == feed_id, CalendarFeed.revoked_at.is_(None)))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kalenderfeed nicht gefunden")
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kalenderfeed nicht gefunden")
    row.last_used_at = utcnow()
    db.commit()
    start = utcnow() - timedelta(days=30)
    end = start + timedelta(days=366)
    events = calendar_feed_events(row, user, start, end, db)
    return Response(
        content=calendar_feed_ics(events, row.name),
        media_type="text/calendar",
        headers={"Content-Disposition": 'inline; filename="familienplan.ics"', "Cache-Control": "no-cache"},
    )


@router.get("/integrations/v1/status")
def integration_status(context=Depends(api_context)):
    token, _ = context
    return {"api_version": "v1", "status": "ok", "server_time": utcnow(), "scopes": token.scopes}


@router.get("/integrations/v1/children")
def integration_children(context=Depends(api_context), db: Session = Depends(get_db)):
    token, user = context; need(token, "read:children")
    ids = allowed_children(token, user, db)
    return [{"id": x.id, "name": x.display_name, "birth_date": x.birth_date,
             "default_responsible_user_id": x.default_responsible_user_id}
            for x in db.scalars(select(Child).where(Child.id.in_(ids)).order_by(Child.display_name))]


def default_stay_periods(child: Child, stays: list[Stay], from_at: datetime, to_at: datetime, responsible_name: str = "Person") -> list[dict]:
    """Represent the child's default home for every gap without an explicit stay."""
    if child.default_responsible_user_id is None:
        return []
    title = f"(Standard) {child.display_name} bei {responsible_name}"
    periods = []
    cursor = from_at
    for stay in sorted(stays, key=lambda item: item.starts_at):
        start, end = max(stay.starts_at, from_at), min(stay.ends_at, to_at)
        if end <= cursor:
            continue
        if start > cursor:
            periods.append({
                "id": None, "event_type": "STAY", "child_id": child.id,
                "responsible_user_id": child.default_responsible_user_id,
                "starts_at": cursor, "ends_at": start, "title": title, "description": None,
                "source": "default", "generated": True,
            })
        cursor = max(cursor, end)
    if cursor < to_at:
        periods.append({
            "id": None, "event_type": "STAY", "child_id": child.id,
            "responsible_user_id": child.default_responsible_user_id,
            "starts_at": cursor, "ends_at": to_at, "title": title, "description": None,
            "source": "default", "generated": True,
        })
    return periods


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
        rows = list(db.scalars(select(Stay).where(Stay.child_id.in_(ids), Stay.status == PlanStatus.CONFIRMED,
            Stay.starts_at < to_at, Stay.ends_at > from_at).order_by(Stay.starts_at)))
        children = {child.id: child for child in db.scalars(select(Child).where(Child.id.in_(ids)))}
        person_ids = {x.responsible_user_id for x in rows} | {child.default_responsible_user_id for child in children.values() if child.default_responsible_user_id}
        people = {person.id: person.display_name for person in db.scalars(select(User).where(User.id.in_(person_ids)))}
        for x in rows:
            title = (x.title or "").strip() or f"{children[x.child_id].display_name} bei {people.get(x.responsible_user_id, 'Person')}"
            result.append({"event_type":"STAY","id":x.id,"child_id":x.child_id,"responsible_user_id":x.responsible_user_id,
                           "starts_at":x.starts_at,"ends_at":x.ends_at,"title":title,"description":x.note,"source":"stay","generated":False})
        for child in children.values():
            result.extend(default_stay_periods(child, [row for row in rows if row.child_id == child.id], from_at, to_at, people.get(child.default_responsible_user_id, "Person")))
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
            is_holiday = x.category == "HOLIDAY"
            if is_holiday and "read:holidays" not in token.scopes: continue
            if not is_holiday and "read:appointments" not in token.scopes: continue
            event_type = "SCHOOL_HOLIDAY" if is_holiday else "SCHOOL" if x.category == "SCHOOL" else x.event_type
            result.append({"event_type":event_type,"custom_type_label":x.custom_type_label,"id":x.id,"child_id":x.child_id,"title":x.title,"description":x.description,"starts_at":x.starts_at,"ends_at":x.ends_at,"all_day":x.all_day})
    if "read:birthdays" in token.scopes and (user.role == Role.ADMIN or "BIRTHDAY" in (user.allowed_event_types or [])):
        birthday_sources = []
        for x in db.scalars(select(Birthday)):
            if x.is_private and ("read:private" not in token.scopes or (x.created_by_id != user.id and user.id not in (x.visible_to_user_ids or []))): continue
            birthday_sources.append((x, {"id": x.id, "source": "birthday"}))
        for x in db.scalars(select(Child).where(Child.id.in_(ids), Child.is_active.is_(True), Child.birth_date.is_not(None))):
            birthday_sources.append((x, {"id": f"child:{x.id}", "source": "child", "child_id": x.id}))
        people_query = select(User).where(User.is_active.is_(True), User.birth_date.is_not(None))
        if user.role != Role.ADMIN:
            people_query = people_query.where(User.id.in_({user.id, *(user.allowed_person_color_ids or [])}))
        for x in db.scalars(people_query):
            birthday_sources.append((x, {"id": f"person:{x.id}", "source": "person", "user_id": x.id}))
        for x, identity in birthday_sources:
            for year in range(from_at.year, to_at.year + 1):
                try: occurrence = x.birth_date.replace(year=year)
                except ValueError: occurrence = x.birth_date.replace(year=year, day=28)
                start = datetime.combine(occurrence, datetime.min.time(), tzinfo=from_at.tzinfo)
                if year >= x.birth_date.year and start < to_at and start + timedelta(days=1) > from_at:
                    result.append({"event_type":"BIRTHDAY", **identity,"title":x.display_name,"starts_at":start,
                                   "ends_at":start+timedelta(days=1),"all_day":True,"age":year-x.birth_date.year,
                                   "first_name":x.first_name or "", "last_name":x.last_name or "",
                                   "display_name":x.display_name,
                                   "full_name":" ".join(part.strip() for part in (x.first_name, x.last_name) if part and part.strip()) or x.display_name,
                                   "birth_date":x.birth_date})
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
    return {"child_id":child_id,"at":at,"responsible_user_id":person_id,
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
