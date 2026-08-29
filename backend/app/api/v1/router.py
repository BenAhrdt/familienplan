import asyncio
import calendar as month_calendar
import hashlib
import re
import time
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import and_, cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import admin, assert_child_access, current_user, require_csrf
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password, new_token, token_hash, utcnow, verify_password
from app.integrations import queue_mail, queue_webhooks
from app.version import VERSION
from app.models.entities import ApplicationSetting, Approval, AuditLog, Birthday, CalendarEvent, CalendarSource, ChangeRequest, Child, ChildUserPermission, Invitation, Notification, Permission, PlanStatus, RecurrenceRule, Role, Session as UserSession, Stay, User
from app.schemas import BirthdayCreate, BirthdayOut, CalendarEventCreate, CalendarEventOut, ChangeDecision, ChangeRequestOut, ChildCreate, ChildOut, ChildUpdate, GroupPlanningCreate, GroupPlanningItem, HolidayOut, InstitutionResult, InvitationAccept, InvitationCreate, InvitationOut, Login, NotificationOut, PermissionSet, PersonAccessOut, PersonAccessUpdate, ProfileUpdate, SectionAccessSetting, SessionOut, SetupAdmin, SetupStatus, StayCreate, StayOut, StayUpdate, ThemeSetting, UserOut

router = APIRouter()
settings = get_settings()
EVENT_TYPES = {"STAY", "BIRTHDAY", "GENERAL", "SCHOOL", "CLEANING", "WASTE", "OTHER"}
_release_cache: tuple[float, dict] | None = None


def _version_parts(value: str) -> tuple[int, ...]:
    numbers = re.match(r"^v?(\d+(?:\.\d+)*)", value.strip())
    return tuple(int(part) for part in numbers.group(1).split(".")) if numbers else (0,)


@router.get("/meta")
async def application_meta(_: User = Depends(current_user)):
    global _release_cache
    repository = (settings.github_repository or "").strip()
    changelog_path = Path(__file__).resolve().parents[4] / "CHANGELOG.md"
    try:
        changelog = changelog_path.read_text(encoding="utf-8")
    except OSError:
        changelog = "# Änderungsprotokoll\n\nDas Änderungsprotokoll ist nicht verfügbar."

    result = {
        "version": VERSION,
        "latest_version": None,
        "update_available": False,
        "release_url": None,
        "repository": repository or None,
        "changelog": changelog,
        "update_check_error": None,
    }
    if not repository or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        return result
    if _release_cache and time.monotonic() - _release_cache[0] < 3600:
        release = _release_cache[1]
    else:
        try:
            async with httpx.AsyncClient(timeout=4, follow_redirects=True) as client:
                response = await client.get(
                    f"https://api.github.com/repos/{repository}/releases/latest",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": f"FamilienPlan/{VERSION}"},
                )
                response.raise_for_status()
                payload = response.json()
                release = {"version": str(payload.get("tag_name", "")).lstrip("v"), "url": payload.get("html_url")}
                _release_cache = (time.monotonic(), release)
        except (httpx.HTTPError, ValueError):
            result["update_check_error"] = "Die Updateprüfung ist derzeit nicht erreichbar."
            return result
    result["latest_version"] = release.get("version")
    result["release_url"] = release.get("url")
    result["update_available"] = _version_parts(str(release.get("version", "0"))) > _version_parts(VERSION)
    return result


def school_event_matches_class(title: str, description: str | None, school_class: str | None) -> bool:
    """Keep school-wide events and reject only events clearly aimed at other classes."""
    target = re.sub(r"[^0-9a-z]", "", (school_class or "").lower())
    if not target:
        return True
    text = f"{title} {description or ''}".lower()
    if re.search(r"\b(?:alle|gesamte\w*)\s+(?:klassen|schule|schüler)", text):
        return True
    class_codes = {
        f"{match.group(1)}{match.group(2)}"
        for match in re.finditer(r"\b([1-9][0-3]?)\s*([a-z])\b", text)
    }
    for match in re.finditer(r"\b([1-9][0-3]?)\s*([a-z])(?:\s*/\s*([a-z]))+", text):
        class_codes.add(f"{match.group(1)}{match.group(2)}")
        if match.group(3):
            class_codes.add(f"{match.group(1)}{match.group(3)}")
    if class_codes:
        return target in class_codes
    grade_match = re.search(r"\b(?:jahrgang|klassenstufe|klasse)\s*([1-9][0-3]?)\b", text)
    if grade_match:
        return target.startswith(grade_match.group(1))
    return True


def normalized_audience(db: Session, creator_id: int, user_ids: list[int] | None) -> list[int] | None:
    """None means visible to everybody; a list is an explicit audience."""
    if user_ids is None:
        return None
    audience = sorted(set(user_ids) | {creator_id})
    existing = set(db.scalars(select(User.id).where(User.id.in_(audience), User.is_active.is_(True))))
    if existing != set(audience):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Sichtbarkeitsauswahl enthält unbekannte Personen")
    return audience


def section_access(db: Session) -> dict[str, list[int]]:
    row = db.get(ApplicationSetting, "section_access")
    value = row.value or {} if row else {}
    return {
        "birthdays": list(value.get("birthdays", [])),
        "waste_collection": list(value.get("waste_collection", [])),
    }


def require_section_access(db: Session, user: User, section: str) -> None:
    if user.role != Role.ADMIN and user.id not in section_access(db).get(section, []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Rubrik ist für dich nicht freigeschaltet")


def recurrence_dates(data: StayCreate) -> list[tuple[datetime, datetime]]:
    occurrences = [(data.starts_at, data.ends_at)]
    if not data.recurrence_interval_weeks:
        return occurrences
    limit = data.recurrence_until or (data.starts_at + timedelta(days=366 * 5))
    duration = data.ends_at - data.starts_at
    cursor = data.starts_at
    while True:
        if data.recurrence_frequency == "MONTHLY":
            month_index = cursor.month - 1 + data.recurrence_interval_weeks
            year, month = cursor.year + month_index // 12, month_index % 12 + 1
            requested_day = data.recurrence_day_of_month or data.starts_at.day
            day = min(requested_day, month_calendar.monthrange(year, month)[1])
            cursor = cursor.replace(year=year, month=month, day=day)
        else:
            cursor += timedelta(weeks=data.recurrence_interval_weeks)
        if cursor > limit:
            break
        occurrences.append((cursor, cursor + duration))
    return occurrences


def audit(db: Session, request: Request, action: str, user_id: int | None = None, target: tuple[str, str] | None = None, metadata: dict | None = None):
    db.add(AuditLog(user_id=user_id, action=action, target_type=target[0] if target else None, target_id=target[1] if target else None, metadata_json=metadata, ip_address=request.client.host if request.client else None))


def notify(db: Session, user_id: int, kind: str, title: str, body: str, request_id: int | None = None):
    notification = Notification(user_id=user_id, kind=kind, title=title, body=body)
    db.add(notification)
    db.flush()
    event_key = f"notification:{notification.id}"
    from app.integrations import mail_config
    app_url = mail_config(db).get("app_url") or settings.app_origin
    action_url = f"{app_url}/calendar?request={request_id}" if request_id else f"{app_url}/calendar"
    queue_mail(db, user_id, event_key, "notification.created", title, f"{body}\n\nÖffne FamilienPlan, um die Anfrage zu prüfen.", action_url)
    queue_webhooks(db, event_key, "notification.created", {"notification_id": notification.id, "user_id": user_id, "kind": kind, "title": title, "body": body})
    return notification


def issue_session(db: Session, response: Response, user: User, remember: bool) -> SessionOut:
    raw = new_token()
    csrf = new_token()
    lifetime = timedelta(days=settings.remember_session_days) if remember else timedelta(hours=settings.session_hours)
    db.add(UserSession(token_hash=token_hash(raw), csrf_token=csrf, user_id=user.id, expires_at=utcnow() + lifetime))
    response.set_cookie("session_token", raw, max_age=int(lifetime.total_seconds()), httponly=True, secure=settings.session_cookie_secure, samesite="lax", path="/")
    return SessionOut(user=user, csrf_token=csrf)


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "postgresql", "connected": True}
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "error", "database": "postgresql", "connected": False})


@router.get("/setup/status", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_db)):
    return SetupStatus(setup_required=(db.scalar(select(func.count(User.id))) == 0))


@router.post("/setup/admin", response_model=SessionOut, status_code=201)
def setup_admin(data: SetupAdmin, request: Request, response: Response, db: Session = Depends(get_db)):
    # SERIALIZABLE plus table lock prevents two simultaneous first-admin registrations.
    db.execute(text("LOCK TABLE users IN ACCESS EXCLUSIVE MODE"))
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(status.HTTP_409_CONFLICT, "Die Ersteinrichtung ist bereits abgeschlossen")
    user = User(username=data.username, display_name=data.display_name, email=str(data.email).lower(), first_name=data.first_name, last_name=data.last_name, password_hash=hash_password(data.password), role=Role.ADMIN)
    db.add(user)
    db.flush()
    audit(db, request, "INITIAL_ADMIN_CREATED", user.id, ("user", str(user.id)))
    result = issue_session(db, response, user, False)
    db.commit()
    return result


@router.post("/auth/login", response_model=SessionOut)
def login(data: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        audit(db, request, "LOGIN_FAILED", target=("username", data.username))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzername oder Passwort ist falsch")
    result = issue_session(db, response, user, data.remember)
    audit(db, request, "LOGIN", user.id)
    db.commit()
    return result


@router.get("/auth/me", response_model=SessionOut)
def me(request: Request, user: User = Depends(current_user)):
    session = getattr(request.state, "auth_session", None)
    return SessionOut(user=user, csrf_token=session.csrf_token if session else "")


@router.post("/auth/logout", status_code=204, dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = getattr(request.state, "auth_session", None)
    if session:
        db.delete(session)
    audit(db, request, "LOGOUT", user.id)
    db.commit()
    response.delete_cookie("session_token", path="/")


@router.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db), _: User = Depends(admin)):
    return list(db.scalars(select(User).order_by(User.display_name)))


@router.get("/people", response_model=list[UserOut])
def people(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)))


@router.get("/birthdays", response_model=list[BirthdayOut])
def birthdays(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Birthday)
    if user.role != Role.ADMIN:
        query = query.where(
            Birthday.is_private.is_(False) | (Birthday.created_by_id == user.id) | cast(Birthday.visible_to_user_ids, JSONB).contains([user.id])
        )
    return list(db.scalars(query.order_by(Birthday.birth_date, Birthday.display_name)))


@router.post("/birthdays", response_model=BirthdayOut, status_code=201, dependencies=[Depends(require_csrf)])
def create_birthday(data: BirthdayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    values = data.model_dump()
    audience = normalized_audience(db, user.id, values.pop("visible_to_user_ids"))
    values["is_private"] = audience is not None
    birthday = Birthday(**values, visible_to_user_ids=audience, created_by_id=user.id)
    db.add(birthday)
    db.flush()
    audit(db, request, "BIRTHDAY_CREATED", user.id, ("birthday", str(birthday.id)))
    db.commit()
    db.refresh(birthday)
    return birthday


@router.put("/birthdays/{birthday_id}", response_model=BirthdayOut, dependencies=[Depends(require_csrf)])
def update_birthday(birthday_id: int, data: BirthdayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    birthday = db.get(Birthday, birthday_id)
    if not birthday or (user.role != Role.ADMIN and birthday.created_by_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Geburtstag nicht gefunden")
    values = data.model_dump()
    audience = normalized_audience(db, birthday.created_by_id, values.pop("visible_to_user_ids"))
    values["visible_to_user_ids"] = audience
    values["is_private"] = audience is not None
    for key, value in values.items():
        setattr(birthday, key, value)
    audit(db, request, "BIRTHDAY_CHANGED", user.id, ("birthday", str(birthday.id)))
    db.commit()
    db.refresh(birthday)
    return birthday


@router.delete("/birthdays/{birthday_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_birthday(birthday_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    birthday = db.get(Birthday, birthday_id)
    if not birthday or (user.role != Role.ADMIN and birthday.created_by_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Geburtstag nicht gefunden")
    audit(db, request, "BIRTHDAY_DELETED", user.id, ("birthday", str(birthday.id)))
    db.delete(birthday)
    db.commit()
    return Response(status_code=204)


@router.get("/settings/theme", response_model=ThemeSetting)
def get_theme(db: Session = Depends(get_db), _: User = Depends(current_user)):
    setting = db.get(ApplicationSetting, "theme")
    value = setting.value or {} if setting else {}
    holiday_color = value.get("holiday_color", "#78B98B")
    # Older installations briefly initialized the new color field as black.
    # Treat that legacy value as unset so holidays remain visibly distinct.
    if holiday_color.upper() == "#000000":
        holiday_color = "#78B98B"
    return ThemeSetting(primary_color=value.get("primary_color", "#3BA4E5"), holiday_color=holiday_color, birthday_color=value.get("birthday_color", "#E0A526"), school_color=value.get("school_color", "#3979B8"))


@router.put("/settings/theme", response_model=ThemeSetting, dependencies=[Depends(require_csrf)])
def update_theme(data: ThemeSetting, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    setting = db.get(ApplicationSetting, "theme")
    if setting:
        setting.value = data.model_dump()
    else:
        db.add(ApplicationSetting(key="theme", value=data.model_dump()))
    audit(db, request, "THEME_CHANGED", user.id, ("setting", "theme"), data.model_dump())
    db.commit()
    return data


@router.get("/settings/sections", response_model=SectionAccessSetting)
def get_section_access(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return SectionAccessSetting(**section_access(db))


@router.put("/settings/sections", response_model=SectionAccessSetting, dependencies=[Depends(require_csrf)])
def update_section_access(data: SectionAccessSetting, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    valid_ids = set(db.scalars(select(User.id).where(User.is_active.is_(True))))
    if (set(data.birthdays) | set(data.waste_collection)) - valid_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Auswahl enthält unbekannte Personen")
    row = db.get(ApplicationSetting, "section_access")
    value = data.model_dump()
    if row:
        row.value = value
    else:
        db.add(ApplicationSetting(key="section_access", value=value))
    audit(db, request, "SECTION_ACCESS_CHANGED", user.id, ("setting", "section_access"), value)
    db.commit()
    return data


@router.get("/waste-appointments", response_model=list[CalendarEventOut])
def waste_appointments(db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_section_access(db, user, "waste_collection")
    query = select(CalendarEvent).where(CalendarEvent.event_type == "WASTE")
    if user.role != Role.ADMIN:
        query = query.where((CalendarEvent.is_private.is_(False)) | (CalendarEvent.created_by_id == user.id) | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]))
    items = list(db.scalars(query.order_by(CalendarEvent.starts_at)))
    representatives: dict[str, CalendarEvent] = {}
    singles: list[CalendarEvent] = []
    for item in items:
        if item.recurrence_group:
            representatives.setdefault(item.recurrence_group, item)
        else:
            singles.append(item)
    return sorted([*singles, *representatives.values()], key=lambda item: item.starts_at)


@router.get("/people/access", response_model=list[PersonAccessOut])
def people_access(db: Session = Depends(get_db), _: User = Depends(admin)):
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)))
    rows = list(db.scalars(select(ChildUserPermission)))
    return [PersonAccessOut(user=item, child_permissions={row.child_id: row.permission for row in rows if row.user_id == item.id}) for item in users]


@router.put("/people/{user_id}/access", response_model=PersonAccessOut, dependencies=[Depends(require_csrf)])
def update_person_access(user_id: int, data: PersonAccessUpdate, request: Request, db: Session = Depends(get_db), actor: User = Depends(admin)):
    person = db.get(User, user_id)
    if not person or not person.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person nicht gefunden")
    if person.id == actor.id and data.role != Role.ADMIN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Die eigenen Administratorrechte können hier nicht entfernt werden")
    username = data.username.strip()
    email = str(data.email).strip().lower()
    if db.scalar(select(User.id).where(func.lower(User.username) == username.lower(), User.id != person.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Benutzername ist bereits vergeben")
    if db.scalar(select(User.id).where(func.lower(User.email) == email, User.id != person.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Diese E-Mail-Adresse ist bereits vergeben")
    person.username = username
    person.display_name = data.display_name.strip()
    person.first_name = data.first_name.strip() if data.first_name else None
    person.last_name = data.last_name.strip() if data.last_name else None
    person.email = email
    person.role = data.role
    if data.color:
        person.color = data.color.upper()
    person.birth_date = data.birth_date
    unknown_types = set(data.allowed_event_types) - EVENT_TYPES
    if unknown_types:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte Terminart")
    person.allowed_event_types = list(dict.fromkeys(data.allowed_event_types))
    existing = list(db.scalars(select(ChildUserPermission).where(ChildUserPermission.user_id == person.id)))
    existing_by_child = {row.child_id: row for row in existing}
    for row in existing:
        if row.child_id not in data.child_permissions:
            db.delete(row)
    for child_id, permission in data.child_permissions.items():
        if not db.get(Child, child_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Kind {child_id} wurde nicht gefunden")
        if child_id in existing_by_child:
            existing_by_child[child_id].permission = permission
        else:
            db.add(ChildUserPermission(child_id=child_id, user_id=person.id, permission=permission))
    audit(db, request, "PERSON_ACCESS_CHANGED", actor.id, ("user", str(person.id)), {"username": person.username, "display_name": person.display_name, "role": data.role.value, "children": list(data.child_permissions)})
    db.commit()
    return PersonAccessOut(user=person, child_permissions=data.child_permissions)


@router.put("/profile", response_model=UserOut, dependencies=[Depends(require_csrf)])
def update_own_profile(data: ProfileUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    user.color = data.color.upper()
    user.birth_date = data.birth_date
    audit(db, request, "OWN_PROFILE_CHANGED", user.id, ("user", str(user.id)), {"color": user.color, "birth_date": data.birth_date.isoformat() if data.birth_date else None})
    db.commit()
    db.refresh(user)
    return user


@router.post("/invitations", response_model=InvitationOut, status_code=201, dependencies=[Depends(require_csrf)])
def invite(data: InvitationCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    raw = new_token()
    invitation = Invitation(email=str(data.email).lower() if data.email else None, role=data.role, display_name=data.display_name, child_permissions={str(key): value.value for key, value in data.child_permissions.items()}, token_hash=token_hash(raw), created_by_id=user.id, expires_at=utcnow() + timedelta(hours=settings.invitation_hours))
    db.add(invitation)
    db.flush()
    invite_url = f"{settings.app_origin}/invite/{raw}"
    if invitation.email:
        recipient = db.scalar(select(User).where(func.lower(User.email) == invitation.email.lower()))
        # New invitees do not have a user row yet, so enqueue directly by address.
        from app.integrations import mail_config
        from app.models.entities import OutboxMessage
        if mail_config(db).get("enabled"):
            db.add(OutboxMessage(channel="email", recipient_key=invitation.email,
                event_key=f"invitation:{invitation.id}", event_type="invitation.created",
                payload={"subject": "Einladung zu FamilienPlan", "body": f"{user.display_name} hat dich zu FamilienPlan eingeladen.\n\nEinladung annehmen: {invite_url}"}))
    audit(db, request, "INVITATION_CREATED", user.id, ("invitation", str(invitation.id)), {"email": invitation.email, "role": invitation.role.value, "children": list(data.child_permissions)})
    db.commit()
    # Returned once so an admin can deliver it when SMTP is not configured.
    return InvitationOut(id=invitation.id, email=invitation.email, expires_at=invitation.expires_at, invite_url=invite_url)


@router.post("/invitations/accept", response_model=SessionOut)
def accept_invite(data: InvitationAccept, request: Request, response: Response, db: Session = Depends(get_db)):
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash(data.token)).with_for_update())
    if not invitation or invitation.used_at or invitation.expires_at <= utcnow():
        raise HTTPException(status.HTTP_410_GONE, "Diese Einladung ist ungültig oder abgelaufen")
    if invitation.email and str(data.email).lower() != invitation.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Die E-Mail-Adresse stimmt nicht mit der Einladung überein")
    if db.scalar(select(User.id).where(func.lower(User.username) == data.username.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Benutzername ist bereits vergeben")
    if db.scalar(select(User.id).where(func.lower(User.email) == str(data.email).lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Diese E-Mail-Adresse ist bereits vergeben")
    user = User(username=data.username, display_name=data.display_name, email=str(data.email).lower(), first_name=data.first_name, last_name=data.last_name, password_hash=hash_password(data.password), role=invitation.role)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc, "orig", None), "diag", None)
        name = getattr(constraint, "constraint_name", None)
        if name == "users_username_key":
            raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Benutzername ist bereits vergeben")
        if name == "users_email_key":
            raise HTTPException(status.HTTP_409_CONFLICT, "Diese E-Mail-Adresse ist bereits vergeben")
        raise HTTPException(status.HTTP_409_CONFLICT, "Das Konto konnte wegen eines Datenkonflikts nicht erstellt werden")
    invitation.used_at = utcnow()
    for child_id, permission in (invitation.child_permissions or {}).items():
        db.add(ChildUserPermission(child_id=int(child_id), user_id=user.id, permission=Permission(permission)))
    audit(db, request, "INVITATION_ACCEPTED", user.id, ("invitation", str(invitation.id)))
    result = issue_session(db, response, user, False)
    db.commit()
    return result


@router.get("/children", response_model=list[ChildOut])
def children(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Child).where(Child.is_active.is_(True)).order_by(Child.display_name)
    if user.role != Role.ADMIN:
        query = query.join(ChildUserPermission).where(ChildUserPermission.user_id == user.id)
    return list(db.scalars(query))


@router.post("/children", response_model=ChildOut, status_code=201, dependencies=[Depends(require_csrf)])
def create_child(data: ChildCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    child = Child(**data.model_dump())
    db.add(child); db.flush()
    audit(db, request, "CHILD_CREATED", user.id, ("child", str(child.id)))
    db.commit()
    return child


@router.put("/children/{child_id}", response_model=ChildOut, dependencies=[Depends(require_csrf)])
def update_child(child_id: int, data: ChildUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    child = db.get(Child, child_id)
    if not child or not child.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kind nicht gefunden")
    for key, value in data.model_dump().items():
        setattr(child, key, value)
    audit(db, request, "CHILD_CHANGED", user.id, ("child", str(child.id)))
    db.commit()
    db.refresh(child)
    return child


@router.get("/holidays", response_model=list[HolidayOut])
async def holidays(year: int, state: str = "HE", _: User = Depends(current_user)):
    if year < 2020 or year > 2100 or len(state) != 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungültiges Jahr oder Bundesland")
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "FamilienPlan/1.0", "Accept": "application/json"}) as client:
            response = await client.get("https://openholidaysapi.org/SchoolHolidays", params={"countryIsoCode": "DE", "subdivisionCode": f"DE-{state.upper()}", "languageIsoCode": "DE", "validFrom": f"{year}-01-01", "validTo": f"{year}-12-31"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Die Ferientage konnten gerade nicht geladen werden")
    return [HolidayOut(name=next((item["text"] for item in row.get("name", []) if item.get("language") == "DE"), row.get("name", [{}])[0].get("text", "Schulferien")), starts_on=row["startDate"], ends_on=row["endDate"]) for row in payload]


@router.get("/public-holidays", response_model=list[HolidayOut])
async def public_holidays(year: int, state: str = "HE", _: User = Depends(current_user)):
    if year < 2020 or year > 2100 or len(state) != 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungültiges Jahr oder Bundesland")
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "FamilienPlan/1.0", "Accept": "application/json"}) as client:
            response = await client.get("https://openholidaysapi.org/PublicHolidays", params={"countryIsoCode": "DE", "subdivisionCode": f"DE-{state.upper()}", "languageIsoCode": "DE", "validFrom": f"{year}-01-01", "validTo": f"{year}-12-31"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Die Feiertage konnten gerade nicht geladen werden")
    return [HolidayOut(name=next((item["text"] for item in row.get("name", []) if item.get("language") == "DE"), row.get("name", [{}])[0].get("text", "Feiertag")), starts_on=row["startDate"], ends_on=row.get("endDate") or row["startDate"]) for row in payload]


class _CalendarLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag == "a":
            values = dict(attrs)
            if values.get("href"):
                self._current_href = values["href"]
                self._current_text = [(values.get("title") or "")]

    def handle_data(self, data: str):
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str):
        if tag == "a" and self._current_href:
            self.links.append((self._current_href, " ".join(self._current_text).strip().lower()))
            self._current_href = None
            self._current_text = []


async def discover_calendar(website: str | None) -> str | None:
    if not website or urlparse(website).scheme not in {"http", "https"}:
        return None
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True, headers={"User-Agent": "FamilienPlan/1.0"}) as client:
            response = await client.get(website)
            response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            return None
        parser = _CalendarLinkParser()
        parser.feed(response.text[:1_000_000])
        for href, title in parser.links:
            candidate = urljoin(str(response.url), href)
            marker = f"{href} {title}".lower()
            if candidate.startswith(("http://", "https://", "webcal://")) and (".ics" in marker or "ical" in marker):
                return candidate
        if "all-in-one-event-calendar" in response.text or "ai1ec_" in response.text:
            wordpress_base = re.search(r"https?://[^\"']+?/(?:(?:wordpress|wp)/)?wp-content/", response.text)
            base = wordpress_base.group(0).rsplit("wp-content/", 1)[0] if wordpress_base else str(response.url)
            return urljoin(base, "?plugin=all-in-one-event-calendar&controller=ai1ec_exporter_controller&action=export_events&no_html=true")
    except (httpx.HTTPError, ValueError):
        pass
    return None


async def discover_related_institution(website: str | None, name: str, city: str) -> InstitutionResult | None:
    if not website or urlparse(website).scheme not in {"http", "https"}:
        return None
    needle = "".join(character for character in name.casefold() if character.isalnum())
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers={"User-Agent": "FamilienPlan/1.0"}) as client:
            response = await client.get(website)
            response.raise_for_status()
        parser = _CalendarLinkParser()
        parser.feed(response.text[:1_000_000])
        for href, label in parser.links:
            normalized = "".join(character for character in f"{href} {label}".casefold() if character.isalnum())
            related_label = any(marker in normalized for marker in ("betreuung", "foerderverein", "förderverein"))
            if (len(needle) >= 3 and needle in normalized) or related_label:
                target = urljoin(str(response.url), href)
                if target.startswith(("http://", "https://")):
                    return InstitutionResult(name=name.strip(), city=city, address=f"Über die Schulhomepage gefunden: {label.strip() or target}", website=target, calendar_url=await discover_calendar(target))
    except (httpx.HTTPError, ValueError):
        pass
    return None


@router.get("/institutions/search", response_model=list[InstitutionResult])
async def search_institutions(kind: str, name: str, city: str, context_url: str | None = None, _: User = Depends(current_user)):
    if kind not in {"school", "care"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte Einrichtungsart")
    if len(name.strip()) < 2 or len(city.strip()) < 2:
        return []
    try:
        async with httpx.AsyncClient(timeout=7, headers={"User-Agent": "FamilienPlan/1.0"}) as client:
            # Nominatim's free-form search works best with the user's actual words.
            # Adding generic terms such as "Schule" can turn a valid partial name
            # into a query with no results (for example Otto-Stückrath, Wiesbaden).
            response = await client.get("https://nominatim.openstreetmap.org/search", params={"q": f"{name.strip()} {city.strip()}", "format": "jsonv2", "addressdetails": 1, "extratags": 1, "namedetails": 1, "limit": 10, "countrycodes": "de"})
            response.raise_for_status()
            places = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Die Einrichtungssuche ist gerade nicht erreichbar")
    candidates = []
    allowed_types = {"school", "college", "kindergarten", "childcare", "community_centre"}
    typed_places = [place for place in places if place.get("type") in allowed_types]
    for place in (typed_places or places)[:6]:
        address = place.get("address") or {}
        extras = place.get("extratags") or {}
        website = extras.get("website") or extras.get("contact:website")
        candidates.append((place, address, website))
    calendars = await asyncio.gather(*(discover_calendar(website) for _, _, website in candidates))
    results = [InstitutionResult(
        name=place.get("name") or place.get("display_name", "").split(",")[0],
        city=address.get("city") or address.get("town") or address.get("village") or city,
        address=place.get("display_name"), state_code=(address.get("ISO3166-2-lvl4") or "-").split("-")[-1] if address.get("ISO3166-2-lvl4") else None, website=website, calendar_url=calendar_url,
    ) for (place, address, website), calendar_url in zip(candidates, calendars)]
    if kind == "care" and context_url:
        related = await discover_related_institution(context_url, name, city)
        if related:
            results.insert(0, related)
        elif urlparse(context_url).scheme in {"http", "https"}:
            results.insert(0, InstitutionResult(
                name=name.strip(),
                city=city.strip(),
                address="Vom angegebenen Homepage-Link übernommen",
                website=context_url,
                calendar_url=await discover_calendar(context_url),
            ))
    # Avoid showing the same homepage twice when both the public directory and
    # the school context point to it.
    unique_results = []
    seen = set()
    for result in results:
        key = (result.website or "", result.name.casefold(), result.city or "")
        if key not in seen:
            seen.add(key)
            unique_results.append(result)
    return unique_results


def _ics_datetime(value: str) -> tuple[datetime, bool]:
    value = value.strip()
    if len(value) == 8:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=utcnow().tzinfo), True
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=utcnow().tzinfo), False
    return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=utcnow().tzinfo), False


@router.post("/children/{child_id}/calendar/sync", dependencies=[Depends(require_csrf)])
async def sync_child_calendar(child_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    child = db.get(Child, child_id)
    if not child or not child.school_calendar_url:
        return {"imported": 0, "message": "Für diese Schule wurde keine öffentliche Kalenderquelle erkannt"}
    url = child.school_calendar_url.replace("webcal://", "https://")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": "FamilienPlan/1.0", "Accept": "text/calendar"}) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Der Schulkalender konnte gerade nicht geladen werden")
    text_data = re.sub(r"\r?\n[ \t]", "", response.text)
    if "BEGIN:VCALENDAR" not in text_data:
        return {"imported": 0, "message": "Die gespeicherte Adresse ist eine Webseite, aber kein öffentlicher iCal-Kalender"}
    source = db.scalar(select(CalendarSource).where(CalendarSource.key == f"child-{child_id}-school"))
    if not source:
        source = CalendarSource(key=f"child-{child_id}-school", name=child.school or "Schulkalender", kind="SCHOOL", url=url)
        db.add(source); db.flush()
    imported = 0
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text_data, re.S):
        fields = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1); fields[key.split(";", 1)[0]] = value.replace("\\,", ",").replace("\\n", "\n")
        if not fields.get("DTSTART") or not fields.get("SUMMARY"):
            continue
        try:
            starts_at, all_day = _ics_datetime(fields["DTSTART"])
            ends_at, _ = _ics_datetime(fields.get("DTEND", "")) if fields.get("DTEND") else (starts_at + (timedelta(days=1) if all_day else timedelta(hours=1)), all_day)
        except ValueError:
            continue
        external_id = fields.get("UID") or hashlib.sha256(f"{fields['SUMMARY']}|{fields['DTSTART']}".encode()).hexdigest()
        event = db.scalar(select(CalendarEvent).where(CalendarEvent.source_id == source.id, CalendarEvent.external_id == external_id))
        if not event:
            event = CalendarEvent(source_id=source.id, external_id=external_id); db.add(event)
        event.child_id, event.title, event.description = child.id, fields["SUMMARY"], fields.get("DESCRIPTION")
        event.starts_at, event.ends_at, event.all_day, event.category, event.event_type, event.url = starts_at, ends_at, all_day, "SCHOOL", "SCHOOL", fields.get("URL")
        imported += 1
    source.last_sync_at, source.last_result, source.last_error = utcnow(), {"events": imported}, None
    audit(db, request, "SCHOOL_CALENDAR_SYNCED", user.id, ("child", str(child_id)), {"events": imported})
    db.commit()
    return {"imported": imported, "message": f"{imported} Schultermine übernommen"}


@router.put("/children/{child_id}/permissions", status_code=204, dependencies=[Depends(require_csrf)])
def set_permission(child_id: int, data: PermissionSet, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    permission = db.scalar(select(ChildUserPermission).where(ChildUserPermission.child_id == child_id, ChildUserPermission.user_id == data.user_id))
    if permission:
        permission.permission = data.permission
    else:
        db.add(ChildUserPermission(child_id=child_id, user_id=data.user_id, permission=data.permission))
    audit(db, request, "CHILD_PERMISSION_CHANGED", user.id, ("child", str(child_id)), {"user_id": data.user_id, "permission": data.permission.value})
    db.commit()


def inferred_recurrence_rule(db: Session, stay: Stay) -> RecurrenceRule | None:
    """Recover the series link for older occurrences that were detached while edited."""
    if stay.recurrence_rule_id:
        return db.get(RecurrenceRule, stay.recurrence_rule_id)
    rules = db.scalars(select(RecurrenceRule).where(
        RecurrenceRule.child_id == stay.child_id,
        RecurrenceRule.starts_at <= stay.starts_at,
        (RecurrenceRule.until_at.is_(None)) | (RecurrenceRule.until_at >= stay.starts_at),
    ))
    matches = []
    for rule in rules:
        interval_match = re.search(r"INTERVAL=(\d+)", rule.rrule)
        interval = int(interval_match.group(1)) if interval_match else 1
        period_seconds = interval * 7 * 24 * 60 * 60
        delta_seconds = int((stay.starts_at - rule.starts_at).total_seconds())
        if delta_seconds >= 0 and delta_seconds % period_seconds == 0:
            matches.append(rule)
    return matches[0] if len(matches) == 1 else None


def stay_payload(db: Session, stay: Stay) -> dict:
    responsible = db.get(User, stay.responsible_user_id)
    rule = inferred_recurrence_rule(db, stay)
    interval_match = re.search(r"INTERVAL=(\d+)", rule.rrule) if rule else None
    day_match = re.search(r"BYMONTHDAY=(\d+)", rule.rrule) if rule else None
    return {
        "id": stay.id, "child_id": stay.child_id, "responsible_user_id": stay.responsible_user_id,
        "responsible_display_name": responsible.display_name if responsible else None,
        "starts_at": stay.starts_at, "ends_at": stay.ends_at, "status": stay.status,
        "note": stay.note, "created_by_id": stay.created_by_id, "recurrence_rule_id": rule.id if rule else None,
        "recurrence_interval_weeks": int(interval_match.group(1)) if interval_match else (1 if rule else None), "recurrence_frequency": ("MONTHLY" if rule and "FREQ=MONTHLY" in rule.rrule else "WEEKLY"), "recurrence_day_of_month": int(day_match.group(1)) if day_match else None, "recurrence_until": rule.until_at if rule else None,
    }


@router.get("/children/{child_id}/stays", response_model=list[StayOut])
def stays(child_id: int, from_at: datetime | None = None, to_at: datetime | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assert_child_access(db, user, child_id)
    query = select(Stay).where(Stay.child_id == child_id, Stay.status == PlanStatus.CONFIRMED)
    if from_at:
        query = query.where(Stay.ends_at > from_at)
    if to_at:
        query = query.where(Stay.starts_at < to_at)
    return [stay_payload(db, item) for item in db.scalars(query.order_by(Stay.starts_at))]


@router.post("/stays", response_model=StayOut, status_code=201, dependencies=[Depends(require_csrf)])
def create_stay(data: StayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if "STAY" not in (user.allowed_event_types or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Die Terminart Aufenthalt ist für dich nicht freigeschaltet")
    assert_child_access(db, user, data.child_id, edit=True)
    if user.role != Role.ADMIN and data.status == PlanStatus.CONFIRMED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bestätigte Aufenthalte erfordern Zustimmung")
    if data.recurrence_interval_weeks and data.recurrence_until:
        duration_minutes = int((data.ends_at - data.starts_at).total_seconds() / 60)
        matching_rule = None
        for candidate in db.scalars(select(RecurrenceRule).where(
            RecurrenceRule.child_id == data.child_id,
            RecurrenceRule.responsible_user_id == data.responsible_user_id,
            RecurrenceRule.duration_minutes == duration_minutes,
        )):
            representative = db.scalar(select(Stay).where(Stay.recurrence_rule_id == candidate.id).order_by(Stay.starts_at).limit(1))
            if representative and (representative.note or "") != (data.note or ""):
                continue
            interval_match = re.search(r"INTERVAL=(\d+)", candidate.rrule)
            interval = int(interval_match.group(1)) if interval_match else 1
            delta_seconds = int((data.starts_at - candidate.starts_at).total_seconds())
            period_seconds = interval * 7 * 24 * 60 * 60
            if interval == data.recurrence_interval_weeks and delta_seconds % period_seconds == 0:
                matching_rule = candidate
                break
        if matching_rule:
            existing = list(db.scalars(select(Stay).where(Stay.recurrence_rule_id == matching_rule.id).order_by(Stay.starts_at)))
            existing_starts = {stay.starts_at for stay in existing}
            extended_backward = False
            if data.starts_at < matching_rule.starts_at:
                backward_cursor = data.starts_at
                step = timedelta(weeks=data.recurrence_interval_weeks)
                while backward_cursor < matching_rule.starts_at:
                    backward_end = backward_cursor + timedelta(minutes=matching_rule.duration_minutes)
                    overlap_stay = db.scalar(select(Stay).where(
                        Stay.child_id == data.child_id,
                        Stay.status == PlanStatus.CONFIRMED,
                        Stay.starts_at < backward_end,
                        Stay.ends_at > backward_cursor,
                    ).order_by(Stay.starts_at).limit(1))
                    if overlap_stay and overlap_stay.starts_at == backward_cursor and overlap_stay.ends_at == backward_end and overlap_stay.responsible_user_id == data.responsible_user_id:
                        overlap_stay.recurrence_rule_id = matching_rule.id
                        existing.append(overlap_stay)
                        existing_starts.add(backward_cursor)
                    elif not overlap_stay:
                        new_stay = Stay(child_id=data.child_id, responsible_user_id=data.responsible_user_id, starts_at=backward_cursor, ends_at=backward_end, status=PlanStatus.CONFIRMED, note=data.note, created_by_id=user.id, recurrence_rule_id=matching_rule.id)
                        db.add(new_stay); existing.append(new_stay); existing_starts.add(backward_cursor)
                    extended_backward = True
                    backward_cursor += step
                matching_rule.starts_at = data.starts_at
            existing.sort(key=lambda item: item.starts_at)
            previous_until = existing[-1].starts_at if existing else matching_rule.starts_at - timedelta(seconds=1)
            step = timedelta(weeks=data.recurrence_interval_weeks)
            cursor_start = matching_rule.starts_at
            added = 0
            while cursor_start <= data.recurrence_until:
                cursor_end = cursor_start + timedelta(minutes=matching_rule.duration_minutes)
                if cursor_start > previous_until and cursor_start not in existing_starts:
                    db.add(Stay(child_id=data.child_id, responsible_user_id=data.responsible_user_id, starts_at=cursor_start, ends_at=cursor_end, status=PlanStatus.CONFIRMED, note=data.note, created_by_id=user.id, recurrence_rule_id=matching_rule.id))
                    added += 1
                cursor_start += step
            if added == 0 and not extended_backward and matching_rule.until_at and data.recurrence_until <= matching_rule.until_at:
                raise HTTPException(status.HTTP_409_CONFLICT, "Diese Serie besteht mit demselben Rhythmus und Zeitraum bereits")
            if not matching_rule.until_at or data.recurrence_until > matching_rule.until_at:
                matching_rule.until_at = data.recurrence_until
            audit(db, request, "STAY_SERIES_EXTENDED", user.id, ("recurrence_rule", str(matching_rule.id)), {"added": added, "until": data.recurrence_until.isoformat()})
            db.commit()
            first = existing[0] if existing else db.scalar(select(Stay).where(Stay.recurrence_rule_id == matching_rule.id).order_by(Stay.starts_at))
            if not first:
                raise HTTPException(status.HTTP_409_CONFLICT, "Für die Serie konnten keine freien Termine angelegt werden")
            return stay_payload(db, first)
    occurrences = recurrence_dates(data)
    rule = None
    if data.recurrence_interval_weeks:
        if data.recurrence_until and data.recurrence_until < data.starts_at:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Das Serienende liegt vor dem Beginn")
        if data.recurrence_until and data.recurrence_until > data.starts_at + timedelta(days=366 * 5):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Serien dürfen höchstens fünf Jahre umfassen")
        rule = RecurrenceRule(child_id=data.child_id, responsible_user_id=data.responsible_user_id, rrule=f"FREQ={data.recurrence_frequency};INTERVAL={data.recurrence_interval_weeks};BYMONTHDAY={data.recurrence_day_of_month or data.starts_at.day}", starts_at=data.starts_at, duration_minutes=int((data.ends_at-data.starts_at).total_seconds()/60), until_at=data.recurrence_until)
        db.add(rule); db.flush()
    created = []
    for starts_at, ends_at in occurrences:
        stay = Stay(child_id=data.child_id, responsible_user_id=data.responsible_user_id, starts_at=starts_at, ends_at=ends_at, status=data.status, note=data.note, created_by_id=user.id, recurrence_rule_id=rule.id if rule else None)
        db.add(stay); created.append(stay)
    db.flush()
    audit(db, request, "STAY_SERIES_CREATED" if rule else "STAY_CREATED", user.id, ("stay", str(created[0].id)), {"status": data.status.value, "occurrences": len(created)})
    db.commit()
    return stay_payload(db, created[0])


@router.post("/stays/conflicts", response_model=list[StayOut], dependencies=[Depends(require_csrf)])
def stay_conflicts(data: StayCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assert_child_access(db, user, data.child_id, edit=True)
    occurrences = recurrence_dates(data)
    found: dict[int, Stay] = {}
    for starts_at, ends_at in occurrences:
        for stay in db.scalars(select(Stay).where(
            Stay.child_id == data.child_id, Stay.status == PlanStatus.CONFIRMED,
            Stay.starts_at < ends_at, Stay.ends_at > starts_at,
        )):
            found[stay.id] = stay
    return [stay_payload(db, stay) for stay in sorted(found.values(), key=lambda item: item.starts_at)]


@router.post("/stay-proposals", response_model=ChangeRequestOut, status_code=201, dependencies=[Depends(require_csrf)])
def propose_new_stay(data: StayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if "STAY" not in (user.allowed_event_types or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Die Terminart Aufenthalt ist für dich nicht freigeschaltet")
    assert_child_access(db, user, data.child_id, edit=True)
    child = db.get(Child, data.child_id)
    if data.recurrence_interval_weeks and data.recurrence_until:
        duration_minutes = int((data.ends_at - data.starts_at).total_seconds() / 60)
        for rule in db.scalars(select(RecurrenceRule).where(
            RecurrenceRule.child_id == data.child_id,
            RecurrenceRule.responsible_user_id == data.responsible_user_id,
            RecurrenceRule.duration_minutes == duration_minutes,
        )):
            match = re.search(r"INTERVAL=(\d+)", rule.rrule)
            interval = int(match.group(1)) if match else 1
            period_seconds = interval * 7 * 24 * 60 * 60
            delta_seconds = int((data.starts_at - rule.starts_at).total_seconds())
            if interval == data.recurrence_interval_weeks and delta_seconds % period_seconds == 0 and rule.until_at and data.recurrence_until <= rule.until_at:
                raise HTTPException(status.HTTP_409_CONFLICT, "Diese Serie besteht mit demselben Rhythmus und Zeitraum bereits")
    affected_id = child.default_responsible_user_id
    if affected_id == user.id:
        affected_id = data.responsible_user_id if data.responsible_user_id != user.id else None
    if not affected_id or affected_id == user.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für diesen Vorschlag gibt es keine andere Person zur Bestätigung")
    occurrences = recurrence_dates(data)
    rule = None
    if data.recurrence_interval_weeks:
        rule = RecurrenceRule(child_id=data.child_id, responsible_user_id=data.responsible_user_id, rrule=f"FREQ={data.recurrence_frequency};INTERVAL={data.recurrence_interval_weeks};BYMONTHDAY={data.recurrence_day_of_month or data.starts_at.day}", starts_at=data.starts_at, duration_minutes=int((data.ends_at-data.starts_at).total_seconds()/60), until_at=data.recurrence_until)
        db.add(rule); db.flush()
    created = []
    for starts_at, ends_at in occurrences:
        stay = Stay(child_id=data.child_id, responsible_user_id=data.responsible_user_id, starts_at=starts_at, ends_at=ends_at, status=PlanStatus.PROPOSED, note=data.note, created_by_id=user.id, recurrence_rule_id=rule.id if rule else None)
        db.add(stay); created.append(stay)
    db.flush()
    item = ChangeRequest(
        object_type="stay", object_id=created[0].id, requested_by_id=user.id,
        affected_user_id=affected_id, status=PlanStatus.PROPOSED, before_data={},
        proposed_data={"action": "CREATE", "stay_ids": [stay.id for stay in created], "starts_at": data.starts_at.isoformat(), "ends_at": data.ends_at.isoformat(), "responsible_user_id": data.responsible_user_id, "note": data.note, "scope": "series" if rule else "occurrence", "recurrence_interval_weeks": data.recurrence_interval_weeks, "recurrence_until": data.recurrence_until.isoformat() if data.recurrence_until else None},
    )
    db.add(item); db.flush()
    notify(db, affected_id, "STAY_PROPOSAL", "Neuer Aufenthaltsvorschlag", f"{user.display_name} schlägt einen neuen Aufenthalt vor.", item.id)
    audit(db, request, "NEW_STAY_PROPOSED", user.id, ("change_request", str(item.id)), {"occurrences": len(created)})
    db.commit(); db.refresh(item)
    return change_request_payload(db, item)


@router.put("/stays/{stay_id}", response_model=list[StayOut], dependencies=[Depends(require_csrf)])
def update_stay(stay_id: int, data: StayUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stay = db.get(Stay, stay_id)
    if not stay:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aufenthalt nicht gefunden")
    assert_child_access(db, user, stay.child_id, edit=True)
    if user.role != Role.ADMIN and stay.status == PlanStatus.CONFIRMED and not getattr(request.state, "approved_change", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bestätigte Aufenthalte müssen über eine Änderungsanfrage geändert werden")
    rule = inferred_recurrence_rule(db, stay)
    rule_id = rule.id if rule else None
    if data.scope != "occurrence" and not rule_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dieser Aufenthalt gehört zu keiner Serie")
    query = select(Stay).where(Stay.id == stay.id)
    if data.scope == "future":
        query = select(Stay).where(((Stay.recurrence_rule_id == rule_id) | (Stay.id == stay.id)), Stay.starts_at >= stay.starts_at)
    elif data.scope == "series":
        query = select(Stay).where((Stay.recurrence_rule_id == rule_id) | (Stay.id == stay.id))
    targets = list(db.scalars(query.order_by(Stay.starts_at)))
    if data.scope == "series" and rule and data.recurrence_interval_weeks:
        if data.recurrence_until and data.recurrence_until < data.starts_at:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Das Serienende liegt vor dem Beginn")
        if data.recurrence_until and data.recurrence_until > data.starts_at + timedelta(days=366 * 5):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Serien dürfen höchstens fünf Jahre umfassen")
        recurrence_frequency = data.recurrence_frequency or "WEEKLY"
        recurrence_day = data.recurrence_day_of_month or data.starts_at.day
        rule.starts_at = data.starts_at
        rule.until_at = data.recurrence_until
        rule.duration_minutes = int((data.ends_at - data.starts_at).total_seconds() / 60)
        rule.responsible_user_id = data.responsible_user_id
        rule.rrule = f"FREQ={recurrence_frequency};INTERVAL={data.recurrence_interval_weeks};BYMONTHDAY={recurrence_day}"
        template = StayCreate(
            child_id=stay.child_id,
            responsible_user_id=data.responsible_user_id,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            status=stay.status,
            note=data.note,
            recurrence_interval_weeks=data.recurrence_interval_weeks,
            recurrence_frequency=recurrence_frequency,
            recurrence_day_of_month=recurrence_day,
            recurrence_until=data.recurrence_until,
        )
        occurrences = recurrence_dates(template)
        for target in targets:
            db.delete(target)
        replacements = []
        for starts_at, ends_at in occurrences:
            replacement = Stay(
                child_id=stay.child_id,
                responsible_user_id=data.responsible_user_id,
                starts_at=starts_at,
                ends_at=ends_at,
                status=stay.status,
                note=data.note,
                created_by_id=stay.created_by_id,
                recurrence_rule_id=rule.id,
            )
            db.add(replacement)
            replacements.append(replacement)
        db.flush()
        audit(db, request, "STAY_SERIES_CHANGED", user.id, ("recurrence_rule", str(rule.id)), {"affected": len(replacements)})
        db.commit()
        return [stay_payload(db, item) for item in replacements]
    original_start, original_end = stay.starts_at, stay.ends_at
    original_responsible_user_id, original_note = stay.responsible_user_id, stay.note
    original_status, original_created_by_id = stay.status, stay.created_by_id
    delta_start, delta_end = data.starts_at - stay.starts_at, data.ends_at - stay.ends_at
    for target in targets:
        new_start, new_end = target.starts_at + delta_start, target.ends_at + delta_end
        target.starts_at, target.ends_at = new_start, new_end
        target.responsible_user_id, target.note = data.responsible_user_id, data.note
    if data.scope == "series" and rule:
        rule.starts_at += delta_start
        if rule.until_at:
            rule.until_at += delta_start
        rule.duration_minutes = int((data.ends_at - data.starts_at).total_seconds() / 60)
        rule.responsible_user_id = data.responsible_user_id
    if data.scope == "occurrence":
        # Editing only part of a multi-day occurrence must not discard the
        # untouched remainder. Detach those pieces from the recurrence as
        # explicit exceptions with the original responsible person.
        if data.starts_at > original_start and data.starts_at < original_end:
            db.add(Stay(
                child_id=stay.child_id,
                responsible_user_id=original_responsible_user_id,
                starts_at=original_start,
                ends_at=data.starts_at,
                status=original_status,
                note=original_note,
                created_by_id=original_created_by_id,
                recurrence_rule_id=None,
            ))
        if data.ends_at < original_end and data.ends_at > original_start:
            db.add(Stay(
                child_id=stay.child_id,
                responsible_user_id=original_responsible_user_id,
                starts_at=data.ends_at,
                ends_at=original_end,
                status=original_status,
                note=original_note,
                created_by_id=original_created_by_id,
                recurrence_rule_id=None,
            ))
        # A deliberately changed occurrence is an explicit exception and must
        # never be regenerated from or moved with the parent series.
        stay.recurrence_rule_id = None
    audit(db, request, "STAY_SERIES_CHANGED" if len(targets) > 1 else "STAY_CHANGED", user.id, ("stay", str(stay.id)), {"scope": data.scope, "affected": len(targets)})
    db.commit()
    return [stay_payload(db, item) for item in targets]


def stay_scope_targets(db: Session, stay: Stay, scope: str) -> list[Stay]:
    rule = inferred_recurrence_rule(db, stay)
    if scope != "occurrence" and not rule:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dieser Aufenthalt gehört zu keiner Serie")
    query = select(Stay).where(Stay.id == stay.id)
    if scope == "future":
        query = select(Stay).where(
            ((Stay.recurrence_rule_id == rule.id) | (Stay.id == stay.id)),
            Stay.starts_at >= stay.starts_at,
        )
    elif scope == "series":
        query = select(Stay).where((Stay.recurrence_rule_id == rule.id) | (Stay.id == stay.id))
    return list(db.scalars(query))


@router.delete("/stays/{stay_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_stay(stay_id: int, scope: str, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    if scope not in {"occurrence", "future", "series"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungültiger Löschumfang")
    stay = db.get(Stay, stay_id)
    if not stay:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aufenthalt nicht gefunden")
    targets = stay_scope_targets(db, stay, scope)
    for target in targets:
        db.delete(target)
    audit(db, request, "STAY_DELETED", user.id, ("stay", str(stay_id)), {"scope": scope, "affected": len(targets)})
    db.commit()
    return Response(status_code=204)


@router.post("/stays/{stay_id}/deletion-proposals", response_model=ChangeRequestOut, status_code=201, dependencies=[Depends(require_csrf)])
def propose_stay_deletion(stay_id: int, scope: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if scope not in {"occurrence", "future", "series"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungültiger Löschumfang")
    stay = db.get(Stay, stay_id)
    if not stay:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aufenthalt nicht gefunden")
    assert_child_access(db, user, stay.child_id, edit=True)
    child = db.get(Child, stay.child_id)
    affected_id = stay.responsible_user_id if stay.responsible_user_id != user.id else child.default_responsible_user_id
    if not affected_id or affected_id == user.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für diese Löschung gibt es keine andere Person zur Bestätigung")
    item = ChangeRequest(
        object_type="stay", object_id=stay.id, requested_by_id=user.id,
        affected_user_id=affected_id, status=PlanStatus.PROPOSED,
        before_data={"starts_at": stay.starts_at.isoformat(), "ends_at": stay.ends_at.isoformat(), "responsible_user_id": stay.responsible_user_id, "note": stay.note},
        proposed_data={"action": "DELETE", "scope": scope},
    )
    db.add(item); db.flush()
    notify(db, affected_id, "STAY_DELETE_PROPOSAL", "Aufenthalt löschen", f"{user.display_name} schlägt vor, einen Aufenthalt zu löschen.", item.id)
    audit(db, request, "STAY_DELETE_PROPOSED", user.id, ("change_request", str(item.id)), {"scope": scope})
    db.commit(); db.refresh(item)
    return change_request_payload(db, item)


def change_request_payload(db: Session, item: ChangeRequest) -> ChangeRequestOut:
    requester, affected = db.get(User, item.requested_by_id), db.get(User, item.affected_user_id)
    stay = db.get(Stay, item.object_id) if item.object_type == "stay" else None
    child = db.get(Child, stay.child_id) if stay else None
    proposed_data = dict(item.proposed_data or {})
    if proposed_data.get("action") == "CREATE" and stay and stay.recurrence_rule_id:
        rule = db.get(RecurrenceRule, stay.recurrence_rule_id)
        if rule:
            match = re.search(r"INTERVAL=(\d+)", rule.rrule)
            proposed_data.setdefault("recurrence_interval_weeks", int(match.group(1)) if match else 1)
            proposed_data.setdefault("recurrence_until", rule.until_at.isoformat() if rule.until_at else None)
    return ChangeRequestOut(id=item.id, object_type=item.object_type, object_id=item.object_id, requested_by_id=item.requested_by_id, requested_by_name=requester.display_name, affected_user_id=item.affected_user_id, affected_user_name=affected.display_name, status=item.status, proposed_data=proposed_data, before_data=item.before_data or {}, child_id=child.id if child else None, child_name=child.display_name if child else None, created_at=item.created_at)


def change_request_details(db: Session, item: ChangeRequest) -> str:
    before, proposed = item.before_data or {}, item.proposed_data or {}
    stay = db.get(Stay, item.object_id)
    child = db.get(Child, stay.child_id) if stay else None
    if proposed.get("action") == "GROUP_CREATE":
        return f"{proposed.get('title') or 'Gruppenplanung'} · {len(proposed.get('items') or [])} Zeiträume"
    parts = [child.display_name if child else "Aufenthalt"]

    def format_date(value):
        if not value:
            return "–"
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return parsed.strftime("%d.%m.%Y %H:%M")

    if proposed.get("action") == "DELETE":
        parts.append(f"Löschung: {format_date(before.get('starts_at'))} – {format_date(before.get('ends_at'))}")
    elif proposed.get("action") == "CREATE":
        person = db.get(User, proposed.get("responsible_user_id"))
        parts.append(f"neu bei {person.display_name if person else 'unbekannt'}")
        parts.append(f"{format_date(proposed.get('starts_at'))} – {format_date(proposed.get('ends_at'))}")
    else:
        if before.get("responsible_user_id") != proposed.get("responsible_user_id"):
            old_person, new_person = db.get(User, before.get("responsible_user_id")), db.get(User, proposed.get("responsible_user_id"))
            parts.append(f"Person: {old_person.display_name if old_person else 'unbekannt'} → {new_person.display_name if new_person else 'unbekannt'}")
        if before.get("starts_at") != proposed.get("starts_at") or before.get("ends_at") != proposed.get("ends_at"):
            parts.append(f"Zeitraum: {format_date(before.get('starts_at'))} – {format_date(before.get('ends_at'))} → {format_date(proposed.get('starts_at'))} – {format_date(proposed.get('ends_at'))}")
        if before.get("note") != proposed.get("note"):
            parts.append(f"Notiz: {before.get('note') or '–'} → {proposed.get('note') or '–'}")
    return " · ".join(parts)


@router.post("/planning-groups", dependencies=[Depends(require_csrf)])
def create_planning_group(data: GroupPlanningCreate, request: Request, mode: str = "proposal", db: Session = Depends(get_db), user: User = Depends(current_user)):
    if mode not in {"direct", "proposal"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungültiger Übernahmemodus")
    if mode == "direct" and user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur Administratoren dürfen eine Planung direkt übernehmen")
    affected = None
    if mode == "proposal":
        if not data.affected_user_id or data.affected_user_id == user.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bitte wähle eine andere Person zur Bestätigung aus")
        affected = db.get(User, data.affected_user_id)
        if not affected or not affected.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die ausgewählte Person wurde nicht gefunden")
    created = []
    item_payloads = []
    for entry in data.items:
        assert_child_access(db, user, entry.child_id, edit=True)
        responsible = db.get(User, entry.responsible_user_id)
        if not responsible or not responsible.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Eine zugeordnete Person wurde nicht gefunden")
        stay = Stay(
            child_id=entry.child_id,
            responsible_user_id=entry.responsible_user_id,
            starts_at=entry.starts_at,
            ends_at=entry.ends_at,
            status=PlanStatus.CONFIRMED if mode == "direct" else PlanStatus.DRAFT,
            note=entry.name,
            created_by_id=user.id,
        )
        db.add(stay)
        db.flush()
        created.append(stay)
        item_payloads.append({**entry.model_dump(mode="json"), "stay_id": stay.id})
    if mode == "proposal":
        group_request = ChangeRequest(
            object_type="group_plan",
            object_id=created[0].id,
            requested_by_id=user.id,
            affected_user_id=affected.id,
            status=PlanStatus.PROPOSED,
            before_data={},
            proposed_data={"action": "GROUP_CREATE", "title": data.title, "stay_ids": [stay.id for stay in created], "items": item_payloads},
        )
        db.add(group_request)
        db.flush()
        notify(db, affected.id, "GROUP_PLAN_PROPOSAL", "Neue Gruppenplanung", f"{user.display_name} hat die Planung „{data.title}“ mit {len(created)} Zeiträumen gesendet.", group_request.id)
        audit(db, request, "GROUP_PLAN_PROPOSED", user.id, ("change_request", str(group_request.id)), {"items": len(created), "affected_user_id": affected.id})
        db.commit()
        return {"mode": mode, "request_id": group_request.id, "created": len(created)}
    audit(db, request, "GROUP_PLAN_CREATED", user.id, ("stay", str(created[0].id)), {"items": len(created)})
    db.commit()
    return {"mode": mode, "created": len(created)}


@router.get("/stay-series", response_model=list[StayOut])
def stay_series(db: Session = Depends(get_db), user: User = Depends(current_user)):
    allowed_child_ids = None
    if user.role != Role.ADMIN:
        allowed_child_ids = list(db.scalars(select(ChildUserPermission.child_id).where(ChildUserPermission.user_id == user.id)))
    query = select(Stay).where(
        Stay.recurrence_rule_id.is_not(None),
        Stay.status == PlanStatus.CONFIRMED,
    ).order_by(Stay.starts_at)
    if user.role != Role.ADMIN:
        query = query.where(Stay.child_id.in_(allowed_child_ids))
    representatives: dict[int, Stay] = {}
    for stay in db.scalars(query):
        representatives.setdefault(stay.recurrence_rule_id, stay)
    return [stay_payload(db, stay) for stay in representatives.values()]


@router.get("/calendar-series", response_model=list[CalendarEventOut])
def calendar_series(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(CalendarEvent).where(CalendarEvent.recurrence_group.is_not(None)).order_by(CalendarEvent.starts_at)
    if user.role != Role.ADMIN:
        allowed_child_ids = list(db.scalars(select(ChildUserPermission.child_id).where(ChildUserPermission.user_id == user.id)))
        query = query.where(
            ((CalendarEvent.child_id.is_(None)) | (CalendarEvent.child_id.in_(allowed_child_ids))),
            ((CalendarEvent.is_private.is_(False)) | (CalendarEvent.created_by_id == user.id)),
        )
    representatives: dict[str, CalendarEvent] = {}
    for event in db.scalars(query):
        representatives.setdefault(event.recurrence_group, event)
    return list(representatives.values())


@router.get("/change-requests", response_model=list[ChangeRequestOut])
def change_requests(db: Session = Depends(get_db), user: User = Depends(current_user)):
    # Repair open requests created by the former recipient logic, which could
    # accidentally address a proposal to its requester instead of the other
    # parent/person involved in the existing stay.
    self_addressed = list(db.scalars(select(ChangeRequest).where(
        ChangeRequest.status.in_([PlanStatus.PROPOSED, PlanStatus.CHANGE_PROPOSED]),
        ChangeRequest.requested_by_id == ChangeRequest.affected_user_id,
        ChangeRequest.object_type == "stay",
    )))
    repaired = False
    for item in self_addressed:
        previous_responsible = item.before_data.get("responsible_user_id") if item.before_data else None
        proposed_responsible = item.proposed_data.get("responsible_user_id") if item.proposed_data else None
        other_user_id = previous_responsible if previous_responsible != item.requested_by_id else proposed_responsible
        stay = db.get(Stay, item.object_id)
        if (not other_user_id or other_user_id == item.requested_by_id) and stay:
            child = db.get(Child, stay.child_id)
            if child and child.default_responsible_user_id != item.requested_by_id:
                other_user_id = child.default_responsible_user_id
        if other_user_id and other_user_id != item.requested_by_id and db.get(User, other_user_id):
            item.affected_user_id = other_user_id
            repaired = True
    if repaired:
        db.commit()
    query = select(ChangeRequest).where(ChangeRequest.status.in_([PlanStatus.PROPOSED, PlanStatus.CHANGE_PROPOSED]))
    if user.role != Role.ADMIN:
        query = query.where((ChangeRequest.affected_user_id == user.id) | (ChangeRequest.requested_by_id == user.id))
    return [change_request_payload(db, item) for item in db.scalars(query.order_by(ChangeRequest.created_at.desc()))]


@router.post("/stays/{stay_id}/proposals", response_model=ChangeRequestOut, status_code=201, dependencies=[Depends(require_csrf)])
def propose_stay_change(stay_id: int, data: StayUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stay = db.get(Stay, stay_id)
    if not stay:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aufenthalt nicht gefunden")
    assert_child_access(db, user, stay.child_id, edit=True)
    # The person who currently has the child in the selected period confirms.
    # If the matched database row already belongs to the requester, look for
    # another overlapping plan and finally use the child's normal residence.
    affected_user_id = stay.responsible_user_id if stay.responsible_user_id != user.id else None
    if not affected_user_id:
        other_stay = db.scalar(select(Stay).where(
            Stay.id != stay.id,
            Stay.child_id == stay.child_id,
            Stay.status == PlanStatus.CONFIRMED,
            Stay.responsible_user_id != user.id,
            Stay.starts_at < data.ends_at,
            Stay.ends_at > data.starts_at,
        ).order_by(Stay.updated_at.desc()).limit(1))
        if other_stay:
            affected_user_id = other_stay.responsible_user_id
    if not affected_user_id:
        child = db.get(Child, stay.child_id)
        if child and child.default_responsible_user_id != user.id:
            affected_user_id = child.default_responsible_user_id
    if not affected_user_id and data.responsible_user_id != user.id:
        affected_user_id = data.responsible_user_id
    affected = db.get(User, affected_user_id) if affected_user_id else None
    if not affected or not affected.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die angefragte Person wurde nicht gefunden")
    if affected.id == user.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für diese Änderung gibt es keine andere Person zur Bestätigung")
    proposed = data.model_dump(mode="json")
    item = ChangeRequest(object_type="stay", object_id=stay.id, requested_by_id=user.id, affected_user_id=affected.id, status=PlanStatus.PROPOSED, before_data={"starts_at": stay.starts_at.isoformat(), "ends_at": stay.ends_at.isoformat(), "responsible_user_id": stay.responsible_user_id, "note": stay.note}, proposed_data=proposed)
    db.add(item); db.flush()
    notify(db, affected.id, "STAY_PROPOSAL", "Neue Aufenthaltsanfrage", f"{user.display_name} schlägt eine Änderung vor. {change_request_details(db, item)}", item.id)
    audit(db, request, "STAY_CHANGE_PROPOSED", user.id, ("change_request", str(item.id)), {"affected_user_id": affected.id, "scope": data.scope})
    db.commit(); db.refresh(item)
    return change_request_payload(db, item)


@router.post("/change-requests/{change_id}/decision", response_model=ChangeRequestOut, dependencies=[Depends(require_csrf)])
def decide_change_request(change_id: int, data: ChangeDecision, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(ChangeRequest, change_id)
    if not item or item.status not in {PlanStatus.PROPOSED, PlanStatus.CHANGE_PROPOSED}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offene Anfrage nicht gefunden")
    if item.affected_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Anfrage ist nicht an dich gerichtet")
    details = change_request_details(db, item)
    section_comment = " · ".join(f"Abschnitt {key}: {value}" for key, value in data.item_comments.items())
    decision_comment = data.comment or section_comment or None
    db.add(Approval(change_request_id=item.id, user_id=user.id, decision=data.decision, comment=decision_comment))
    if data.decision == "APPROVE":
        request.state.approved_change = True
        item.status = PlanStatus.CONFIRMED
        is_group = item.proposed_data.get("action") == "GROUP_CREATE"
        notify(db, item.requested_by_id, "STAY_APPROVED", "Gruppenplanung bestätigt" if is_group else "Aufenthaltsanfrage bestätigt", f"{user.display_name} hat deinen Vorschlag bestätigt. {details}{f' · Kommentare: {decision_comment}' if decision_comment else ''}")
        if item.proposed_data.get("action") == "GROUP_CREATE":
            proposed_stays = [db.get(Stay, stay_id) for stay_id in item.proposed_data.get("stay_ids", [])]
            confirmed_count = 0
            for stay in proposed_stays:
                if stay:
                    stay.status = PlanStatus.CONFIRMED
                    confirmed_count += 1
            if not confirmed_count:
                raise HTTPException(status.HTTP_409_CONFLICT, "Die Gruppenplanung enthält keine verfügbaren Einträge mehr")
            db.commit()
        elif item.proposed_data.get("action") == "CREATE":
            proposed_stays = [db.get(Stay, stay_id) for stay_id in item.proposed_data.get("stay_ids", [item.object_id])]
            confirmed_count = 0
            for stay in proposed_stays:
                if not stay:
                    continue
                stay.status = PlanStatus.CONFIRMED
                confirmed_count += 1
            if not confirmed_count:
                raise HTTPException(status.HTTP_409_CONFLICT, "Alle vorgeschlagenen Termine sind bereits belegt")
            db.commit()
        elif item.proposed_data.get("action") == "DELETE":
            stay = db.get(Stay, item.object_id)
            if stay:
                for target in stay_scope_targets(db, stay, item.proposed_data.get("scope", "occurrence")):
                    db.delete(target)
            db.commit()
        else:
            update_stay(item.object_id, StayUpdate.model_validate(item.proposed_data), request, db, user)
    elif data.decision == "REJECT":
        item.status = PlanStatus.REJECTED
        if item.proposed_data.get("action") == "GROUP_CREATE":
            for stay_id in item.proposed_data.get("stay_ids", []):
                stay = db.get(Stay, stay_id)
                if stay:
                    db.delete(stay)
        elif item.proposed_data.get("action") == "CREATE":
            rule_ids = set()
            for stay_id in item.proposed_data.get("stay_ids", [item.object_id]):
                stay = db.get(Stay, stay_id)
                if stay:
                    if stay.recurrence_rule_id:
                        rule_ids.add(stay.recurrence_rule_id)
                    db.delete(stay)
            db.flush()
            for rule_id in rule_ids:
                if not db.scalar(select(Stay.id).where(Stay.recurrence_rule_id == rule_id).limit(1)):
                    rule = db.get(RecurrenceRule, rule_id)
                    if rule:
                        db.delete(rule)
        notify(db, item.requested_by_id, "STAY_REJECTED", "Gruppenplanung abgelehnt" if item.proposed_data.get("action") == "GROUP_CREATE" else "Aufenthaltsanfrage abgelehnt", f"{user.display_name} hat den Vorschlag abgelehnt. {details} · Begründung: {decision_comment}")
        db.commit()
    else:
        if not data.counter_proposal:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für einen Gegenvorschlag fehlen die neuen Angaben")
        previous_requester = item.requested_by_id
        item.requested_by_id, item.affected_user_id = user.id, previous_requester
        if item.proposed_data.get("action") == "GROUP_CREATE":
            counter = data.counter_proposal if isinstance(data.counter_proposal, dict) else data.counter_proposal.model_dump(mode="json")
            if counter.get("action") != "GROUP_CREATE" or not counter.get("items"):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Der Gegenvorschlag enthält keine Planungsabschnitte")
            for stay_id in item.proposed_data.get("stay_ids", []):
                stay = db.get(Stay, stay_id)
                if stay:
                    db.delete(stay)
            db.flush()
            new_stay_ids = []
            new_items = []
            for raw_entry in counter["items"]:
                entry = GroupPlanningItem.model_validate(raw_entry)
                assert_child_access(db, user, entry.child_id, edit=True)
                if not db.get(User, entry.responsible_user_id):
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Eine zugeordnete Person wurde nicht gefunden")
                stay = Stay(child_id=entry.child_id, responsible_user_id=entry.responsible_user_id, starts_at=entry.starts_at, ends_at=entry.ends_at, status=PlanStatus.DRAFT, note=entry.name, created_by_id=user.id)
                db.add(stay)
                db.flush()
                new_stay_ids.append(stay.id)
                new_items.append({**entry.model_dump(mode="json"), "stay_id": stay.id, "comment": raw_entry.get("comment")})
            item.object_id = new_stay_ids[0]
            item.proposed_data = {"action": "GROUP_CREATE", "title": counter.get("title") or item.proposed_data.get("title"), "stay_ids": new_stay_ids, "items": new_items}
        else:
            item.proposed_data = data.counter_proposal.model_dump(mode="json") if hasattr(data.counter_proposal, "model_dump") else data.counter_proposal
        item.status = PlanStatus.CHANGE_PROPOSED
        notify(db, previous_requester, "STAY_COUNTER", "Gegenvorschlag zur Gruppenplanung" if item.proposed_data.get("action") == "GROUP_CREATE" else "Gegenvorschlag zum Aufenthalt", f"{user.display_name} hat einen Gegenvorschlag gesendet. {change_request_details(db, item)}{f' · Kommentare: {decision_comment}' if decision_comment else ''}", item.id)
        db.commit()
    db.refresh(item)
    return change_request_payload(db, item)


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return list(db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)))


@router.post("/notifications/read-all", status_code=204, dependencies=[Depends(require_csrf)])
def read_all_notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    unread = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
    )
    read_at = utcnow()
    for notification in unread:
        notification.read_at = read_at
    db.commit()
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read", status_code=204, dependencies=[Depends(require_csrf)])
def read_notification(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    notification = db.get(Notification, notification_id)
    if not notification or notification.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benachrichtigung nicht gefunden")
    notification.read_at = utcnow()
    db.commit()
    return Response(status_code=204)


@router.get("/calendar", response_model=list[CalendarEventOut])
def calendar(from_at: datetime, to_at: datetime, db: Session = Depends(get_db), user: User = Depends(current_user)):
    allowed_child_ids = None
    if user.role != Role.ADMIN:
        allowed_child_ids = list(db.scalars(select(ChildUserPermission.child_id).where(ChildUserPermission.user_id == user.id)))
    query = select(CalendarEvent).where(CalendarEvent.starts_at < to_at, CalendarEvent.ends_at > from_at)
    if user.role != Role.ADMIN:
        query = query.where((CalendarEvent.is_private.is_(False)) | (CalendarEvent.created_by_id == user.id) | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]))
    if allowed_child_ids is not None:
        query = query.where((CalendarEvent.child_id.is_(None)) | (CalendarEvent.child_id.in_(allowed_child_ids)))
    result = list(db.scalars(query.order_by(CalendarEvent.starts_at)))
    children_by_id = {
        child.id: child
        for child in db.scalars(select(Child).where(Child.id.in_({event.child_id for event in result if event.child_id})))
    }
    return [
        event for event in result
        if event.event_type != "SCHOOL"
        or not event.child_id
        or school_event_matches_class(event.title, event.description, children_by_id.get(event.child_id).school_class if children_by_id.get(event.child_id) else None)
    ]


@router.get("/search")
def global_search(q: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    term = q.strip()
    if len(term) < 2:
        return []
    ignored_words = {"bei", "am", "im", "in", "der", "die", "das", "und"}
    words = [
        word
        for word in re.findall(r"[\w@.+-]+", term.lower(), flags=re.UNICODE)
        if word not in ignored_words
    ]
    if not words:
        return []

    def matches(*columns):
        return and_(
            *[
                or_(*[column.ilike(f"%{word}%") for column in columns])
                for word in words
            ]
        )

    now = utcnow()
    allowed_child_ids = None
    if user.role != Role.ADMIN:
        allowed_child_ids = list(
            db.scalars(
                select(ChildUserPermission.child_id).where(
                    ChildUserPermission.user_id == user.id,
                )
            )
        )
    child_query = select(Child).where(
        Child.is_active.is_(True),
        matches(
            Child.display_name,
            Child.first_name,
            Child.last_name,
            Child.school,
            Child.care,
            Child.notes,
        ),
    )
    if allowed_child_ids is not None:
        child_query = child_query.where(Child.id.in_(allowed_child_ids))
    found_children = list(db.scalars(child_query.limit(10)))

    event_query = select(CalendarEvent).where(
        matches(CalendarEvent.title, CalendarEvent.description),
    )
    if user.role != Role.ADMIN:
        event_query = event_query.where(
            (CalendarEvent.is_private.is_(False))
            | (CalendarEvent.created_by_id == user.id),
            (CalendarEvent.child_id.is_(None))
            | (CalendarEvent.child_id.in_(allowed_child_ids or [])),
        )
    found_events = [
        *db.scalars(
            event_query.where(CalendarEvent.ends_at >= now)
            .order_by(CalendarEvent.starts_at.asc())
            .limit(60)
        ),
        *db.scalars(
            event_query.where(CalendarEvent.ends_at < now)
            .order_by(CalendarEvent.starts_at.desc())
            .limit(20)
        ),
    ]

    stay_query = (
        select(Stay, Child, User)
        .join(Child, Child.id == Stay.child_id)
        .join(User, User.id == Stay.responsible_user_id)
        .where(
            Stay.status == PlanStatus.CONFIRMED,
            matches(Child.display_name, User.display_name, Stay.note),
        )
    )
    if allowed_child_ids is not None:
        stay_query = stay_query.where(Stay.child_id.in_(allowed_child_ids))
    found_stays = [
        *db.execute(
            stay_query.where(Stay.ends_at >= now)
            .order_by(Stay.starts_at.asc())
            .limit(60)
        ).all(),
        *db.execute(
            stay_query.where(Stay.ends_at < now)
            .order_by(Stay.starts_at.desc())
            .limit(20)
        ).all(),
    ]

    results = [
        {
            "kind": "child",
            "id": child.id,
            "title": child.display_name,
            "subtitle": child.school or child.care or "Kind",
            "starts_at": None,
        }
        for child in found_children
    ]
    if user.role == Role.ADMIN:
        found_people = list(
            db.scalars(
                select(User)
                .where(
                    User.is_active.is_(True),
                    matches(
                        User.display_name,
                        User.first_name,
                        User.last_name,
                        User.username,
                        User.email,
                    ),
                )
                .limit(10)
            )
        )
        results.extend(
            {
                "kind": "person",
                "id": person.id,
                "title": person.display_name,
                "subtitle": "Person",
                "starts_at": None,
            }
            for person in found_people
        )
    birthday_query = select(Birthday).where(
        matches(
            Birthday.display_name,
            Birthday.first_name,
            Birthday.last_name,
        )
    )
    if user.role != Role.ADMIN:
        birthday_query = birthday_query.where(
            Birthday.is_private.is_(False) | (Birthday.created_by_id == user.id)
        )
    for birthday in db.scalars(birthday_query.limit(20)):
        birthday_day = min(
            birthday.birth_date.day,
            month_calendar.monthrange(now.year, birthday.birth_date.month)[1],
        )
        next_date = datetime(
            now.year,
            birthday.birth_date.month,
            birthday_day,
            tzinfo=now.tzinfo,
        )
        if next_date < now:
            next_year = now.year + 1
            birthday_day = min(
                birthday.birth_date.day,
                month_calendar.monthrange(next_year, birthday.birth_date.month)[1],
            )
            next_date = datetime(
                next_year,
                birthday.birth_date.month,
                birthday_day,
                tzinfo=now.tzinfo,
            )
        results.append(
            {
                "kind": "birthday",
                "id": birthday.id,
                "title": birthday.display_name,
                "subtitle": "Privater Geburtstag" if birthday.is_private else "Geburtstag",
                "starts_at": next_date,
            }
        )
    results.extend(
        {
            "kind": "event",
            "id": event.id,
            "title": event.title,
            "subtitle": "Privater Termin" if event.is_private else "Termin",
            "starts_at": event.starts_at,
        }
        for event in found_events
    )
    results.extend(
        {
            "kind": "stay",
            "id": stay.id,
            "title": f"{child.display_name} bei {person.display_name}",
            "subtitle": stay.note or "Aufenthalt",
            "starts_at": stay.starts_at,
        }
        for stay, child, person in found_stays
    )
    def search_order(item):
        starts_at = item["starts_at"]
        if starts_at is None:
            return (0, 0)
        if starts_at >= now:
            return (1, starts_at.timestamp())
        return (2, -starts_at.timestamp())

    return sorted(results, key=search_order)[:40]


@router.post("/calendar", response_model=CalendarEventOut, status_code=201, dependencies=[Depends(require_csrf)])
def create_calendar_event(data: CalendarEventCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    waste_section_allowed = data.event_type == "WASTE" and user.id in section_access(db)["waste_collection"]
    if user.role == Role.VIEWER and not waste_section_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Keine Bearbeitungsberechtigung")
    if data.child_id is not None:
        assert_child_access(db, user, data.child_id, edit=not waste_section_allowed)
    if data.event_type not in (user.allowed_event_types or []) and not waste_section_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Terminart ist für dich nicht freigeschaltet")
    values = data.model_dump(exclude={"starts_at", "ends_at", "recurrence_day_of_month"})
    values["visible_to_user_ids"] = normalized_audience(db, user.id, values.get("visible_to_user_ids"))
    values["is_private"] = values["visible_to_user_ids"] is not None
    frequency = values.pop("recurrence_frequency")
    interval = values.pop("recurrence_interval")
    until = values.pop("recurrence_until")
    duration = data.ends_at - data.starts_at
    limit = until or (data.starts_at + timedelta(days=366 * 5))
    cursor = data.starts_at
    group = str(uuid.uuid4()) if frequency and interval else None
    created = []
    while True:
        event = CalendarEvent(
            **values,
            starts_at=cursor,
            ends_at=cursor + duration,
            source_id=None,
            created_by_id=user.id,
            recurrence_group=group,
            recurrence_frequency=frequency,
            recurrence_interval=interval,
            recurrence_until=until,
        )
        db.add(event)
        created.append(event)
        if not frequency or not interval:
            break
        if frequency == "MONTHLY":
            month_index = cursor.month - 1 + interval
            year, month = cursor.year + month_index // 12, month_index % 12 + 1
            requested_day = data.recurrence_day_of_month or data.starts_at.day
            cursor = cursor.replace(year=year, month=month, day=min(requested_day, month_calendar.monthrange(year, month)[1]))
        else:
            cursor += timedelta(weeks=interval)
        if cursor > limit:
            break
    db.flush()
    audit(db, request, "CALENDAR_EVENT_SERIES_CREATED" if group else "CALENDAR_EVENT_CREATED", user.id, ("calendar_event", str(created[0].id)), {"occurrences": len(created)})
    db.commit()
    return created[0]


@router.put("/calendar/{event_id}", response_model=CalendarEventOut, dependencies=[Depends(require_csrf)])
def update_calendar_event(event_id: int, data: CalendarEventCreate, request: Request, scope: str = "occurrence", db: Session = Depends(get_db), user: User = Depends(current_user)):
    if scope not in {"occurrence", "future", "series"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungültiger Änderungsumfang")
    event = db.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    if event.is_private and event.created_by_id != user.id and user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    if user.role != Role.ADMIN and event.created_by_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du darfst diesen Termin nicht bearbeiten")
    waste_section_allowed = data.event_type == "WASTE" and user.id in section_access(db)["waste_collection"]
    if data.event_type not in (user.allowed_event_types or []) and not waste_section_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Terminart ist für dich nicht freigeschaltet")
    data.visible_to_user_ids = normalized_audience(db, event.created_by_id or user.id, data.visible_to_user_ids)
    data.is_private = data.visible_to_user_ids is not None
    if data.child_id is not None:
        assert_child_access(db, user, data.child_id, edit=not waste_section_allowed)
    if event.recurrence_group and data.recurrence_frequency and data.recurrence_interval and scope in {"future", "series"}:
        old_group = event.recurrence_group
        group = old_group if scope == "series" else str(uuid.uuid4())
        creator_id = event.created_by_id
        duration = data.ends_at - data.starts_at
        limit = data.recurrence_until or (data.starts_at + timedelta(days=366 * 5))
        targets_query = select(CalendarEvent).where(CalendarEvent.recurrence_group == old_group)
        if scope == "future":
            targets_query = targets_query.where(CalendarEvent.starts_at >= event.starts_at)
            for previous in db.scalars(select(CalendarEvent).where(CalendarEvent.recurrence_group == old_group, CalendarEvent.starts_at < event.starts_at)):
                previous.recurrence_until = event.starts_at - timedelta(seconds=1)
        for old_event in db.scalars(targets_query):
            db.delete(old_event)
        replacements = []
        cursor = data.starts_at
        while cursor <= limit:
            replacement = CalendarEvent(
                source_id=None, child_id=data.child_id, title=data.title,
                description=data.description, starts_at=cursor, ends_at=cursor + duration,
                all_day=data.all_day, category=data.category, color=data.color,
                is_private=data.is_private, event_type=data.event_type,
                custom_type_label=data.custom_type_label,
                visible_to_user_ids=data.visible_to_user_ids, created_by_id=creator_id,
                recurrence_group=group, recurrence_frequency=data.recurrence_frequency,
                recurrence_interval=data.recurrence_interval,
                recurrence_until=data.recurrence_until,
            )
            db.add(replacement)
            replacements.append(replacement)
            if data.recurrence_frequency == "MONTHLY":
                month_index = cursor.month - 1 + data.recurrence_interval
                year, month = cursor.year + month_index // 12, month_index % 12 + 1
                requested_day = data.recurrence_day_of_month or data.starts_at.day
                cursor = cursor.replace(year=year, month=month, day=min(requested_day, month_calendar.monthrange(year, month)[1]))
            else:
                cursor += timedelta(weeks=data.recurrence_interval)
        db.flush()
        audit(db, request, "CALENDAR_EVENT_SERIES_CHANGED", user.id, ("calendar_event_series", group), {"scope": scope, "occurrences": len(replacements)})
        db.commit()
        return replacements[0]
    event.title = data.title
    event.description = data.description
    event.starts_at = data.starts_at
    event.ends_at = data.ends_at
    event.all_day = data.all_day
    event.category = data.category
    event.child_id = data.child_id
    event.color = data.color
    event.is_private = data.is_private
    event.event_type = data.event_type
    event.custom_type_label = data.custom_type_label
    event.visible_to_user_ids = data.visible_to_user_ids
    if event.recurrence_group and scope == "occurrence":
        event.recurrence_group = None
        event.recurrence_frequency = None
        event.recurrence_interval = None
        event.recurrence_until = None
    audit(db, request, "CALENDAR_EVENT_CHANGED", user.id, ("calendar_event", str(event.id)))
    db.commit()
    db.refresh(event)
    return event


@router.delete("/calendar/{event_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_calendar_event(event_id: int, request: Request, scope: str = "occurrence", db: Session = Depends(get_db), user: User = Depends(current_user)):
    if scope not in {"occurrence", "future", "series"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungültiger Löschumfang")
    event = db.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    if user.role != Role.ADMIN and event.created_by_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du darfst diesen Termin nicht löschen")
    targets = [event]
    if scope == "series" and event.recurrence_group:
        targets = list(db.scalars(select(CalendarEvent).where(CalendarEvent.recurrence_group == event.recurrence_group)))
    elif scope == "future" and event.recurrence_group:
        targets = list(db.scalars(select(CalendarEvent).where(CalendarEvent.recurrence_group == event.recurrence_group, CalendarEvent.starts_at >= event.starts_at)))
    for target in targets:
        db.delete(target)
    audit(db, request, "CALENDAR_EVENT_SERIES_DELETED" if len(targets) > 1 else "CALENDAR_EVENT_DELETED", user.id, ("calendar_event", str(event_id)), {"scope": scope, "affected": len(targets)})
    db.commit()
    return Response(status_code=204)


@router.get("/children/{child_id}/location/today")
def location_today(child_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assert_child_access(db, user, child_id)
    now = utcnow()
    child = db.get(Child, child_id)
    stay = db.scalar(select(Stay).where(Stay.child_id == child_id, Stay.status == PlanStatus.CONFIRMED, Stay.starts_at <= now, Stay.ends_at > now).order_by(Stay.starts_at.desc()))
    responsible = db.get(User, stay.responsible_user_id) if stay else db.get(User, child.default_responsible_user_id) if child.default_responsible_user_id else None
    return {"child": {"id": child.id, "display_name": child.display_name}, "date": now.date(), "with": ({"id": responsible.id, "display_name": responsible.display_name} if responsible else None), "from": stay.starts_at if stay else None, "until": stay.ends_at if stay else None, "status": stay.status.value.lower() if stay else None}
