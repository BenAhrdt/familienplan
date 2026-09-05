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
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Cookie, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, cast, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import admin, assert_child_access, current_user, require_csrf
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password, new_token, token_hash, utcnow, verify_password
from app.integrations import queue_mail
from app.push import queue_push, vapid_config
from app.version import VERSION
from app.models.entities import ApiToken, ApplicationSetting, Approval, AuditLog, Birthday, CalendarEvent, CalendarEventAttachment, CalendarSource, ChangeRequest, Child, ChildUserPermission, HolidayPlan, HolidayPlanSegment, Invitation, Notification, PasswordResetToken, Permission, PlanStatus, PushSubscription, RecurrenceRule, Role, Session as UserSession, Stay, User
from app.schemas import AuditPushSetting, BirthdayCreate, BirthdayOut, CalendarColorPreferences, CalendarDisplayPreferences, CalendarEventAttachmentOut, CalendarEventCreate, CalendarEventOut, CalendarTypeSettings, ChangeDecision, ChangeRequestOut, ChildCreate, ChildOut, ChildUpdate, GroupPlanningCreate, GroupPlanningItem, HolidayOut, InstitutionResult, InvitationAccept, InvitationCreate, InvitationOut, Login, NotificationOut, PasswordChange, PasswordForgot, PasswordReset, PermissionSet, PersonAccessOut, PersonAccessUpdate, ProfileUpdate, PushSubscriptionCreate, SectionAccessSetting, SessionOut, SetupAdmin, SetupStatus, StayCreate, StayOut, StayUpdate, ThemeSetting, UserOut, WasteCalendarSetting
from app.waste_calendar import awido_options, delete_waste_config, get_waste_config, list_waste_configs, save_waste_config, sync_waste_calendar

router = APIRouter()
settings = get_settings()
EVENT_TYPES = {"STAY", "BIRTHDAY", "GENERAL", "SCHOOL", "CLEANING", "WASTE", "PRIVATE", "OTHER"}
CHILDLESS_EVENT_TYPES = {"BIRTHDAY", "CLEANING", "WASTE"}
ATTACHMENT_MAX_BYTES = 15 * 1024 * 1024
ATTACHMENT_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/webp",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text", "text/plain",
}
_release_cache: tuple[float, dict] | None = None


def require_event_view(db: Session, user: User, event_id: int) -> CalendarEvent:
    event = db.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    visible_private = event.created_by_id == user.id or user.id in (event.visible_to_user_ids or [])
    if (event.event_type == "PRIVATE" or event.is_private) and not visible_private and user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    if user.role != Role.ADMIN:
        if event.child_id and not db.scalar(select(ChildUserPermission.id).where(ChildUserPermission.child_id == event.child_id, ChildUserPermission.user_id == user.id)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
        if event.event_type not in (user.allowed_event_types or []) and event.event_type not in {"PRIVATE", "OTHER"}:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
        if event.event_type == "OTHER":
            custom = next((item for item in custom_calendar_types(db) if item["name"] == event.custom_type_label), None)
            if not custom or user.id not in set(custom.get("visible_to_user_ids", []) + custom.get("editable_by_user_ids", [])):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    return event


def _version_parts(value: str) -> tuple[int, ...]:
    numbers = re.match(r"^v?(\d+(?:\.\d+)*)", value.strip())
    return tuple(int(part) for part in numbers.group(1).split(".")) if numbers else (0,)


@router.get("/meta")
async def application_meta(refresh: bool = False, user: User = Depends(current_user)):
    global _release_cache
    if refresh:
        if user.role != Role.ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur Administratoren dürfen die Updateprüfung erzwingen")
        _release_cache = None
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


@router.post("/system/update", status_code=202, dependencies=[Depends(require_csrf)])
def start_system_update(request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    marker = settings.upload_dir.resolve() / ".update-requested"
    marker.parent.mkdir(parents=True, exist_ok=True)
    if marker.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ein Update wurde bereits angefordert")
    marker.write_text(f"requested_by={user.id}\nfrom_version={VERSION}\n", encoding="utf-8")
    audit(db, request, "SYSTEM_UPDATE_REQUESTED", user.id, ("system", "familienplan"), {"from_version": VERSION})
    db.commit()
    return {"started": True, "from_version": VERSION}


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
    waste_users = set(value.get("waste_collection", []))
    for calendar in list_waste_configs(db):
        waste_users.update(calendar.get("visible_to_user_ids", []))
    return {
        "birthdays": list(value.get("birthdays", [])),
        "waste_collection": sorted(waste_users),
    }


def upsert_application_setting(db: Session, key: str, value: dict) -> None:
    db.execute(
        pg_insert(ApplicationSetting)
        .values(key=key, value=value)
        .on_conflict_do_update(index_elements=[ApplicationSetting.key], set_={"value": value})
    )


def custom_calendar_types(db: Session) -> list[dict]:
    row = db.get(ApplicationSetting, "custom_calendar_types")
    return list(row.value or []) if row else []


def custom_calendar_type_for_label(db: Session, label: str | None) -> dict | None:
    normalized = (label or "").strip().casefold()
    return next((item for item in custom_calendar_types(db) if item.get("name", "").strip().casefold() == normalized), None)


def visible_custom_calendar_labels(db: Session, user: User) -> set[str]:
    if user.role == Role.ADMIN:
        return {item["name"] for item in custom_calendar_types(db)}
    return {item["name"] for item in custom_calendar_types(db)
            if user.id in item.get("visible_to_user_ids", []) or user.id in item.get("editable_by_user_ids", [])}


def require_section_access(db: Session, user: User, section: str) -> None:
    if user.role != Role.ADMIN and user.id not in section_access(db).get(section, []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Rubrik ist für dich nicht freigeschaltet")


def visible_person_ids(user: User) -> set[int]:
    """People a user may select or whose person data may be listed."""
    return {user.id, *(user.allowed_person_color_ids or [])}


def assert_person_visible(db: Session, user: User, person_id: int) -> User:
    person = db.get(User, person_id)
    if not person or not person.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die ausgewählte Person wurde nicht gefunden")
    if user.role != Role.ADMIN and person.id not in visible_person_ids(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Person ist für dich nicht freigegeben")
    return person


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


AUDIT_PUSH_EXCLUDED_ACTIONS = {
    "LOGIN", "LOGOUT", "LOGIN_FAILED",
    "NEW_STAY_PROPOSED", "STAY_CHANGE_PROPOSED", "STAY_DELETE_PROPOSED", "GROUP_PLAN_PROPOSED",
    "AUDIT_PUSH_CHANGED",
}
AUDIT_PUSH_ACTION_LABELS = {
    "PASSWORD_CHANGED": "hat das eigene Passwort geändert", "PASSWORD_RESET_REQUESTED": "hat einen Passwort-Reset angefordert", "PASSWORD_RESET_COMPLETED": "hat das Passwort zurückgesetzt",
    "INITIAL_ADMIN_CREATED": "hat FamilienPlan eingerichtet",
    "PERSON_ACCESS_CHANGED": "hat die Rechte einer Person geändert",
    "PERSON_DELETED": "hat eine Person gelöscht",
    "INVITATION_CREATED": "hat eine Einladung erstellt", "INVITATION_RENEWED": "hat einen Einladungslink erneuert", "INVITATION_SENT": "hat eine Einladung versendet", "INVITATION_ACCEPTED": "hat eine Einladung angenommen",
    "CHILD_CREATED": "hat ein Kind angelegt", "CHILD_CHANGED": "hat ein Kind geändert", "CHILD_PERMISSION_CHANGED": "hat Kinderrechte geändert",
    "STAY_CREATED": "hat eine Betreuungszeit angelegt", "STAY_CHANGED": "hat eine Betreuungszeit geändert", "STAY_DELETED": "hat eine Betreuungszeit gelöscht",
    "STAY_SERIES_CREATED": "hat eine Betreuungsserie angelegt", "STAY_SERIES_CHANGED": "hat eine Betreuungsserie geändert", "STAY_SERIES_EXTENDED": "hat eine Betreuungsserie verlängert",
    "CALENDAR_EVENT_CREATED": "hat einen Termin angelegt", "CALENDAR_EVENT_CHANGED": "hat einen Termin geändert", "CALENDAR_EVENT_DELETED": "hat einen Termin gelöscht",
    "CALENDAR_EVENT_SERIES_CREATED": "hat eine Terminserie angelegt", "CALENDAR_EVENT_SERIES_CHANGED": "hat eine Terminserie geändert", "CALENDAR_EVENT_SERIES_DELETED": "hat eine Terminserie gelöscht",
    "CALENDAR_EVENT_ATTACHMENT_ADDED": "hat einem Termin einen Anhang hinzugefügt", "CALENDAR_EVENT_ATTACHMENT_DELETED": "hat einen Terminanhang gelöscht",
    "BIRTHDAY_CREATED": "hat einen Geburtstag angelegt", "BIRTHDAY_CHANGED": "hat einen Geburtstag geändert", "BIRTHDAY_DELETED": "hat einen Geburtstag gelöscht",
    "SECTION_ACCESS_CHANGED": "hat Rubrikenfreigaben geändert", "CALENDAR_EVENT_TYPES_CHANGED": "hat Terminarten und Freigaben geändert", "THEME_CHANGED": "hat die globale Darstellung geändert",
    "PERSONAL_CALENDAR_COLORS_CHANGED": "hat persönliche Kalenderfarben geändert", "PERSONAL_CALENDAR_DISPLAY_CHANGED": "hat die persönliche Kalenderanzeige geändert", "OWN_PROFILE_CHANGED": "hat das eigene Profil geändert",
    "SCHOOL_CALENDAR_SYNCED": "hat einen Schulkalender synchronisiert", "WASTE_CALENDAR_SYNCED": "hat einen Abfallkalender synchronisiert", "CALENDAR_SOURCE_SYNCED": "hat einen externen Kalender synchronisiert",
    "WASTE_CALENDAR_CREATED": "hat einen Abfallkalender angelegt", "WASTE_CALENDAR_SETTINGS_CHANGED": "hat einen Abfallkalender geändert", "WASTE_CALENDAR_DELETED": "hat einen Abfallkalender gelöscht",
    "SYSTEM_UPDATE_REQUESTED": "hat ein Systemupdate gestartet", "IMPERSONATION_STARTED": "hat die Ansicht einer Person übernommen", "IMPERSONATION_STOPPED": "hat die übernommene Ansicht beendet",
}


def audit_push_enabled(db: Session, user_id: int) -> bool:
    row = db.get(ApplicationSetting, f"audit_push_{user_id}")
    return bool(row and (row.value or {}).get("enabled"))


def queue_audit_pushes(db: Session, request: Request, entry: AuditLog, actor: User | None) -> None:
    if not actor or entry.action in AUDIT_PUSH_EXCLUDED_ACTIONS or getattr(request.state, "approved_change", False):
        return
    app_url = settings.app_origin.rstrip("/")
    label = AUDIT_PUSH_ACTION_LABELS.get(entry.action, entry.action.lower().replace("_", " "))
    for recipient in db.scalars(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True), User.id != actor.id)):
        if audit_push_enabled(db, recipient.id):
            queue_push(db, recipient.id, f"audit:{entry.id}", f"Logbuch: {actor.display_name}", f"{actor.display_name} {label}.", app_url)


def audit(db: Session, request: Request, action: str, user_id: int | None = None, target: tuple[str, str] | None = None, metadata: dict | None = None):
    details = dict(metadata or {})
    actor = None
    if user_id:
        actor = db.get(User, user_id)
        if actor:
            details.setdefault("_actor_name", actor.display_name)
    entry = AuditLog(user_id=user_id, action=action, target_type=target[0] if target else None, target_id=target[1] if target else None, metadata_json=details or None, ip_address=request.client.host if request.client else None)
    db.add(entry)
    db.flush()
    queue_audit_pushes(db, request, entry, actor)


def notify(db: Session, user_id: int, kind: str, title: str, body: str, request_id: int | None = None):
    notification = Notification(user_id=user_id, kind=kind, title=title, body=body)
    db.add(notification)
    db.flush()
    event_key = f"notification:{notification.id}"
    from app.integrations import mail_config
    app_url = mail_config(db).get("app_url") or settings.app_origin
    action_url = f"{app_url}/calendar?request={request_id}" if request_id else f"{app_url}/calendar"
    queue_mail(db, user_id, event_key, "notification.created", title, f"{body}\n\nÖffne FamilienPlan, um die Anfrage zu prüfen.", action_url)
    queue_push(db, user_id, event_key, title, body, action_url)
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


@router.post("/auth/password/forgot", status_code=202)
def forgot_password(data: PasswordForgot, request: Request, db: Session = Depends(get_db)):
    """Always answer identically so an address cannot be tested for membership."""
    user = db.scalar(select(User).where(func.lower(User.email) == str(data.email).lower(), User.is_active.is_(True), User.is_pending.is_(False)))
    if user:
        raw = new_token()
        db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)).values(used_at=utcnow()))
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash(raw), expires_at=utcnow() + timedelta(hours=1)))
        from app.integrations import mail_config
        app_url = mail_config(db).get("app_url") or settings.app_origin
        queue_mail(db, user.id, f"password-reset:{user.id}:{uuid.uuid4().hex}", "password.reset", "Passwort für FamilienPlan zurücksetzen", "Über diesen Link kannst du innerhalb einer Stunde ein neues Passwort festlegen. Falls du das nicht angefordert hast, ignoriere diese Nachricht.", f"{app_url}/reset-password/{raw}")
        audit(db, request, "PASSWORD_RESET_REQUESTED", user.id, ("user", str(user.id)))
    db.commit()
    return {"message": "Wenn die E-Mail-Adresse registriert ist, wurde ein Link zum Zurücksetzen versendet."}


@router.post("/auth/password/reset")
def reset_password(data: PasswordReset, request: Request, db: Session = Depends(get_db)):
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(data.token)).with_for_update())
    if not reset or reset.used_at or reset.expires_at <= utcnow():
        raise HTTPException(status.HTTP_410_GONE, "Dieser Link ist ungültig oder abgelaufen")
    user = db.get(User, reset.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_410_GONE, "Dieser Link ist ungültig oder abgelaufen")
    user.password_hash = hash_password(data.password)
    reset.used_at = utcnow()
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    audit(db, request, "PASSWORD_RESET_COMPLETED", user.id, ("user", str(user.id)))
    db.commit()
    return {"message": "Das Passwort wurde geändert. Du kannst dich jetzt anmelden."}


@router.get("/auth/me", response_model=SessionOut)
def me(request: Request, user: User = Depends(current_user), admin_session_token: str | None = Cookie(default=None)):
    session = getattr(request.state, "auth_session", None)
    return SessionOut(user=user, csrf_token=session.csrf_token if session else "", impersonating=bool(admin_session_token))


@router.post("/auth/logout", status_code=204, dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = getattr(request.state, "auth_session", None)
    if session:
        db.delete(session)
    audit(db, request, "LOGOUT", user.id)
    db.commit()
    response.delete_cookie("session_token", path="/")
    response.delete_cookie("admin_session_token", path="/")


@router.post("/people/{user_id}/impersonate", response_model=SessionOut, dependencies=[Depends(require_csrf)])
def impersonate(user_id: int, request: Request, response: Response, db: Session = Depends(get_db), actor: User = Depends(admin), session_token: str | None = Cookie(default=None)):
    target = db.get(User, user_id)
    if not target or not target.is_active or target.is_pending:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person ist noch nicht für die Anmeldung freigeschaltet")
    if target.role == Role.ADMIN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Administratorkonten können nicht simuliert werden")
    if not session_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Die Admin-Sitzung konnte nicht übernommen werden")
    result = issue_session(db, response, target, False)
    response.set_cookie("admin_session_token", session_token, max_age=settings.session_hours * 3600,
        httponly=True, secure=settings.session_cookie_secure, samesite="strict", path="/")
    audit(db, request, "IMPERSONATION_STARTED", actor.id, ("user", str(target.id)))
    db.commit()
    result.impersonating = True
    return result


@router.post("/auth/impersonation/stop", response_model=SessionOut, dependencies=[Depends(require_csrf)])
def stop_impersonation(request: Request, response: Response, db: Session = Depends(get_db), current: User = Depends(current_user), admin_session_token: str | None = Cookie(default=None)):
    original = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(admin_session_token or "")))
    original_admin = original.user if original and original.expires_at > utcnow() else None
    if not original_admin or original_admin.role != Role.ADMIN or not original_admin.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Die ursprüngliche Admin-Sitzung ist nicht mehr gültig")
    simulated_session = getattr(request.state, "auth_session", None)
    if simulated_session:
        db.delete(simulated_session)
    remaining = max(1, int((original.expires_at - utcnow()).total_seconds()))
    response.set_cookie("session_token", admin_session_token, max_age=remaining, httponly=True,
        secure=settings.session_cookie_secure, samesite="lax", path="/")
    response.delete_cookie("admin_session_token", path="/")
    audit(db, request, "IMPERSONATION_STOPPED", original_admin.id, ("user", str(current.id)))
    db.commit()
    return SessionOut(user=original_admin, csrf_token=original.csrf_token, impersonating=False)


@router.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db), _: User = Depends(admin)):
    return list(db.scalars(select(User).order_by(User.display_name)))


@router.get("/people", response_model=list[UserOut])
def people(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(User).where(User.is_active.is_(True))
    if user.role != Role.ADMIN:
        query = query.where(User.id.in_(visible_person_ids(user)))
    return list(db.scalars(query.order_by(User.display_name)))


@router.get("/birthdays", response_model=list[BirthdayOut])
def birthdays(db: Session = Depends(get_db), user: User = Depends(current_user)):
    has_section_access = user.role == Role.ADMIN or user.id in section_access(db)["birthdays"]
    if not has_section_access and "BIRTHDAY" not in (user.allowed_event_types or []):
        return []
    query = select(Birthday)
    if user.role != Role.ADMIN:
        query = query.where(
            Birthday.is_private.is_(False) | (Birthday.created_by_id == user.id) | cast(Birthday.visible_to_user_ids, JSONB).contains([user.id])
        )
    return list(db.scalars(query.order_by(Birthday.birth_date, Birthday.display_name)))


def require_birthday_write(db: Session, user: User) -> None:
    if user.role == Role.ADMIN or (user.role != Role.VIEWER and "BIRTHDAY" in (user.allowed_event_types or [])):
        return
    require_section_access(db, user, "birthdays")


@router.post("/calendar/{event_id}/birthday", response_model=BirthdayOut, dependencies=[Depends(require_csrf)])
def convert_calendar_birthday(event_id: int, data: BirthdayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_birthday_write(db, user)
    event = require_event_view(db, user, event_id)
    if event.source_id:
        raise HTTPException(422, "Nur selbst angelegte Termine können umgewandelt werden")
    if user.role != Role.ADMIN and event.created_by_id != user.id:
        raise HTTPException(403, "Du darfst diesen Termin nicht umwandeln")
    targets = list(db.scalars(select(CalendarEvent).where(CalendarEvent.recurrence_group == event.recurrence_group))) if event.recurrence_group else [event]
    if db.scalar(select(CalendarEventAttachment.id).where(CalendarEventAttachment.event_id.in_([x.id for x in targets])).limit(1)):
        raise HTTPException(422, "Bitte sichere und entferne zuerst die Dokumente der bisherigen Geburtstagstermine.")
    values = data.model_dump()
    audience = normalized_audience(db, event.created_by_id, values.pop("visible_to_user_ids"))
    values["is_private"] = audience is not None
    birthday = Birthday(**values, visible_to_user_ids=audience, created_by_id=event.created_by_id)
    db.add(birthday)
    db.flush()
    audit(db, request, "BIRTHDAY_CREATED", user.id, ("birthday", str(birthday.id)), {
        "name": birthday.display_name, "birth_date": birthday.birth_date.isoformat(),
        "previous_events": [{"id": x.id, "title": x.title, "description": x.description, "starts_at": x.starts_at.isoformat()} for x in targets],
    })
    for target in targets:
        db.delete(target)
    db.commit()
    db.refresh(birthday)
    return birthday


@router.post("/birthdays", response_model=BirthdayOut, status_code=201, dependencies=[Depends(require_csrf)])
def create_birthday(data: BirthdayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_birthday_write(db, user)
    values = data.model_dump()
    audience = normalized_audience(db, user.id, values.pop("visible_to_user_ids"))
    values["is_private"] = audience is not None
    birthday = Birthday(**values, visible_to_user_ids=audience, created_by_id=user.id)
    db.add(birthday)
    db.flush()
    audit(db, request, "BIRTHDAY_CREATED", user.id, ("birthday", str(birthday.id)), {"name": birthday.display_name, "birth_date": birthday.birth_date.isoformat()})
    db.commit()
    db.refresh(birthday)
    return birthday


@router.put("/birthdays/{birthday_id}", response_model=BirthdayOut, dependencies=[Depends(require_csrf)])
def update_birthday(birthday_id: int, data: BirthdayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_birthday_write(db, user)
    birthday = db.get(Birthday, birthday_id)
    if not birthday or (user.role != Role.ADMIN and birthday.created_by_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Geburtstag nicht gefunden")
    values = data.model_dump()
    audience = normalized_audience(db, birthday.created_by_id, values.pop("visible_to_user_ids"))
    values["visible_to_user_ids"] = audience
    values["is_private"] = audience is not None
    for key, value in values.items():
        setattr(birthday, key, value)
    audit(db, request, "BIRTHDAY_CHANGED", user.id, ("birthday", str(birthday.id)), {"name": birthday.display_name, "birth_date": birthday.birth_date.isoformat(), "visibility": birthday.visible_to_user_ids})
    db.commit()
    db.refresh(birthday)
    return birthday


@router.delete("/birthdays/{birthday_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_birthday(birthday_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_birthday_write(db, user)
    birthday = db.get(Birthday, birthday_id)
    if not birthday or (user.role != Role.ADMIN and birthday.created_by_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Geburtstag nicht gefunden")
    audit(db, request, "BIRTHDAY_DELETED", user.id, ("birthday", str(birthday.id)), {"name": birthday.display_name, "birth_date": birthday.birth_date.isoformat()})
    db.delete(birthday)
    db.commit()
    return Response(status_code=204)


@router.get("/settings/theme", response_model=ThemeSetting)
def get_theme(db: Session = Depends(get_db), _: User = Depends(current_user)):
    setting = db.get(ApplicationSetting, "theme")
    value = setting.value or {} if setting else {}
    return ThemeSetting(primary_color=value.get("primary_color", "#3BA4E5"), holiday_color=value.get("holiday_color", "#78B98B"), birthday_color=value.get("birthday_color", "#E0A526"), school_color=value.get("school_color", "#3979B8"))


@router.put("/settings/theme", response_model=ThemeSetting, dependencies=[Depends(require_csrf)])
def update_theme(data: ThemeSetting, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    values = data.model_dump()
    upsert_application_setting(db, "theme", values)
    audit(db, request, "THEME_CHANGED", user.id, ("setting", "theme"), values)
    db.commit()
    stored = db.scalar(select(ApplicationSetting).where(ApplicationSetting.key == "theme").execution_options(populate_existing=True))
    return ThemeSetting(**stored.value)


def resolved_calendar_colors(db: Session, user_id: int) -> dict:
    theme = get_theme(db, None)
    waste = get_waste_config(db)
    defaults = {
        "holiday_color": theme.holiday_color,
        "birthday_color": theme.birthday_color,
        "school_color": theme.school_color,
        "waste_color": waste.get("color", "#5C8B58"),
    }
    row = db.get(ApplicationSetting, f"calendar_colors_{user_id}")
    personal = dict(row.value or {}) if row else {}
    return {**defaults, **personal}


@router.get("/settings/calendar-colors", response_model=CalendarColorPreferences)
def get_calendar_colors(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return resolved_calendar_colors(db, user.id)


@router.put("/settings/calendar-colors", response_model=CalendarColorPreferences, dependencies=[Depends(require_csrf)])
def update_calendar_colors(data: CalendarColorPreferences, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    key = f"calendar_colors_{user.id}"
    values = data.model_dump()
    upsert_application_setting(db, key, values)
    audit(db, request, "PERSONAL_CALENDAR_COLORS_CHANGED", user.id, ("setting", key), values)
    db.commit()
    stored = db.scalar(select(ApplicationSetting).where(ApplicationSetting.key == key).execution_options(populate_existing=True))
    return CalendarColorPreferences(**stored.value)


@router.get("/settings/calendar-display", response_model=CalendarDisplayPreferences)
def get_calendar_display(db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(ApplicationSetting, f"calendar_display_{user.id}")
    return CalendarDisplayPreferences(**(row.value if row else {}))


@router.put("/settings/calendar-display", response_model=CalendarDisplayPreferences, dependencies=[Depends(require_csrf)])
def update_calendar_display(data: CalendarDisplayPreferences, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    key = f"calendar_display_{user.id}"
    values = data.model_dump()
    upsert_application_setting(db, key, values)
    audit(db, request, "PERSONAL_CALENDAR_DISPLAY_CHANGED", user.id, ("setting", key), values)
    db.commit()
    return data


@router.get("/calendar-event-types")
def available_calendar_event_types(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{**item, "can_create": user.role == Role.ADMIN or user.id in item.get("editable_by_user_ids", [])}
            for item in custom_calendar_types(db)
            if user.role == Role.ADMIN or user.id in item.get("visible_to_user_ids", []) or user.id in item.get("editable_by_user_ids", [])]


@router.get("/settings/calendar-event-types", response_model=CalendarTypeSettings)
def get_calendar_event_type_settings(db: Session = Depends(get_db), _: User = Depends(admin)):
    users = list(db.scalars(select(User).where(User.is_active.is_(True), User.role != Role.ADMIN)))
    standard = {event_type: [user.id for user in users if event_type in (user.allowed_event_types or [])]
                for event_type in sorted(EVENT_TYPES - {"PRIVATE"})}
    return {"standard_type_user_ids": standard, "custom_types": custom_calendar_types(db)}


@router.put("/settings/calendar-event-types", response_model=CalendarTypeSettings, dependencies=[Depends(require_csrf)])
def update_calendar_event_type_settings(data: CalendarTypeSettings, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    valid_users = set(db.scalars(select(User.id).where(User.is_active.is_(True))))
    selected_users = {entry for entries in data.standard_type_user_ids.values() for entry in entries}
    selected_users.update(entry for item in data.custom_types for entry in [*item.visible_to_user_ids, *item.editable_by_user_ids])
    if selected_users - valid_users:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Terminarten enthalten unbekannte Personen")
    unknown_standard = set(data.standard_type_user_ids) - (EVENT_TYPES - {"PRIVATE"})
    if unknown_standard:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte Standard-Terminart")
    ids = [item.id for item in data.custom_types]
    names = [item.name.strip().casefold() for item in data.custom_types]
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "IDs und Namen eigener Terminarten müssen eindeutig sein")
    previous = {item.get("id"): item for item in custom_calendar_types(db)}
    removed = set(previous) - set(ids)
    for removed_id in removed:
        old_name = previous[removed_id].get("name")
        if db.scalar(select(CalendarEvent.id).where(CalendarEvent.event_type == "OTHER", CalendarEvent.custom_type_label == old_name).limit(1)):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Die Terminart „{old_name}“ wird noch von Terminen verwendet und kann nicht gelöscht werden")
    stored_custom = []
    for item in data.custom_types:
        value = item.model_dump()
        value["name"] = value["name"].strip()
        value["visible_to_user_ids"] = sorted(set(value["visible_to_user_ids"]) | set(value["editable_by_user_ids"]))
        old = previous.get(value["id"])
        if old and old.get("name") != value["name"]:
            for event in db.scalars(select(CalendarEvent).where(CalendarEvent.event_type == "OTHER", CalendarEvent.custom_type_label == old.get("name"))):
                event.custom_type_label = value["name"]
        stored_custom.append(value)
    for person in db.scalars(select(User).where(User.is_active.is_(True), User.role != Role.ADMIN)):
        person.allowed_event_types = sorted(event_type for event_type in EVENT_TYPES - {"PRIVATE"}
                                            if person.id in data.standard_type_user_ids.get(event_type, []))
    upsert_application_setting(db, "custom_calendar_types", stored_custom)
    audit(db, request, "CALENDAR_EVENT_TYPES_CHANGED", user.id, ("setting", "custom_calendar_types"), {"custom_types": [item["name"] for item in stored_custom]})
    db.commit()
    return {"standard_type_user_ids": data.standard_type_user_ids, "custom_types": stored_custom}


@router.get("/settings/sections", response_model=SectionAccessSetting)
def get_section_access(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return SectionAccessSetting(**section_access(db))


@router.get("/audit-log")
def get_audit_log(user_id: int | None = None, action: str | None = None, limit: int = 100, offset: int = 0,
                  db: Session = Depends(get_db), _: User = Depends(admin)):
    limit = min(max(limit, 1), 250)
    offset = max(offset, 0)
    query = select(AuditLog, User.display_name).outerjoin(User, User.id == AuditLog.user_id)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    rows = db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit + 1)).all()
    return {
        "items": [{
            "id": entry.id,
            "user_id": entry.user_id,
            "user_name": display_name or (entry.metadata_json or {}).get("_actor_name") or "System / unbekannt",
            "action": entry.action,
            "target_type": entry.target_type,
            "target_id": entry.target_id,
            "details": {key: value for key, value in (entry.metadata_json or {}).items() if not key.startswith("_")},
            "ip_address": entry.ip_address,
            "created_at": entry.created_at,
        } for entry, display_name in rows[:limit]],
        "has_more": len(rows) > limit,
        "next_offset": offset + min(len(rows), limit),
    }


@router.get("/settings/audit-push", response_model=AuditPushSetting)
def get_audit_push_setting(db: Session = Depends(get_db), user: User = Depends(admin)):
    return AuditPushSetting(enabled=audit_push_enabled(db, user.id))


@router.put("/settings/audit-push", response_model=AuditPushSetting, dependencies=[Depends(require_csrf)])
def update_audit_push_setting(data: AuditPushSetting, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    upsert_application_setting(db, f"audit_push_{user.id}", data.model_dump())
    audit(db, request, "AUDIT_PUSH_CHANGED", user.id, ("setting", "audit_push"), data.model_dump())
    db.commit()
    return data


@router.put("/settings/sections", response_model=SectionAccessSetting, dependencies=[Depends(require_csrf)])
def update_section_access(data: SectionAccessSetting, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    valid_ids = set(db.scalars(select(User.id).where(User.is_active.is_(True))))
    if (set(data.birthdays) | set(data.waste_collection)) - valid_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Auswahl enthält unbekannte Personen")
    value = data.model_dump()
    upsert_application_setting(db, "section_access", value)
    audit(db, request, "SECTION_ACCESS_CHANGED", user.id, ("setting", "section_access"), value)
    db.commit()
    stored = db.scalar(select(ApplicationSetting).where(ApplicationSetting.key == "section_access").execution_options(populate_existing=True))
    return SectionAccessSetting(**stored.value)


@router.get("/waste-appointments", response_model=list[CalendarEventOut])
def waste_appointments(db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_section_access(db, user, "waste_collection")
    query = select(CalendarEvent).where(CalendarEvent.event_type == "WASTE", CalendarEvent.source_id.is_(None))
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


def waste_calendar_out(value: dict, user: User) -> dict:
    result = dict(value)
    owner = result.get("owner_user_id")
    result["can_manage"] = user.role == Role.ADMIN or owner == user.id
    result["can_delete"] = user.role == Role.ADMIN or owner == user.id
    result["hidden_for_me"] = user.id in value.get("hidden_for_user_ids", [])
    return result


def accessible_waste_calendar(db: Session, calendar_id: str, user: User, manage: bool = False) -> dict:
    value = get_waste_config(db, calendar_id)
    if not value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Abfallkalender nicht gefunden")
    owner = value.get("owner_user_id")
    can_manage = user.role == Role.ADMIN or owner == user.id
    if manage and not can_manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur Eigentümer oder Administratoren dürfen diesen Abfallkalender verwalten")
    if not can_manage and user.id not in value.get("visible_to_user_ids", []):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Abfallkalender nicht gefunden")
    return value


@router.get("/waste-calendars", response_model=list[WasteCalendarSetting])
def waste_calendar_settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [waste_calendar_out(value, user) for value in list_waste_configs(db)
            if user.role == Role.ADMIN or value.get("owner_user_id") == user.id or user.id in value.get("visible_to_user_ids", [])]


@router.post("/waste-calendars", response_model=WasteCalendarSetting, status_code=201, dependencies=[Depends(require_csrf)])
def create_waste_calendar(data: WasteCalendarSetting, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    valid_ids = set(db.scalars(select(User.id).where(User.is_active.is_(True))))
    if set(data.visible_to_user_ids) - valid_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Auswahl enthält unbekannte Personen")
    value = data.model_dump(exclude={"id", "owner_user_id", "can_manage", "can_delete", "hidden_for_me", "last_sync_at", "last_result", "last_error"})
    value.update({"id": str(uuid.uuid4()), "owner_user_id": user.id, "hidden_for_user_ids": [], "last_sync_at": None, "last_result": None, "last_error": None})
    save_waste_config(db, value)
    audit(db, request, "WASTE_CALENDAR_CREATED", user.id, ("waste_calendar", value["id"]), {"name": value["name"], "visibility": value["visible_to_user_ids"]})
    db.commit()
    return waste_calendar_out(value, user)


@router.get("/calendar-sources/status")
def calendar_source_status(db: Session = Depends(get_db), _: User = Depends(admin)):
    return [{
        "id": source.id, "name": source.name, "kind": source.kind,
        "last_sync_at": source.last_sync_at, "last_result": source.last_result,
        "last_error": source.last_error, "active": source.is_active,
    } for source in db.scalars(select(CalendarSource).order_by(CalendarSource.kind, CalendarSource.name))]


@router.post("/calendar-sources/{source_id}/sync", dependencies=[Depends(require_csrf)])
async def synchronize_calendar_source(source_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    source = db.get(CalendarSource, source_id)
    if not source or not source.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kalenderquelle nicht gefunden")
    try:
        if source.kind == "WASTE":
            calendar_id = "legacy" if source.key == "waste-calendar-import" else source.key.removeprefix("waste-calendar-import-")
            result = await sync_waste_calendar(db, calendar_id)
        elif source.kind == "SCHOOL":
            match = re.fullmatch(r"child-(\d+)-school", source.key)
            child = db.get(Child, int(match.group(1))) if match else None
            if not child or not child.school_calendar_url:
                raise HTTPException(status.HTTP_409_CONFLICT, "Die zugehörige Schulkalender-Adresse ist nicht mehr eingerichtet")
            result = await synchronize_child_calendar(db, child)
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Diese Kalenderquelle unterstützt noch keine manuelle Synchronisierung")
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    audit(db, request, "CALENDAR_SOURCE_SYNCED", user.id, ("calendar_source", str(source.id)), result)
    db.commit()
    return result


@router.put("/waste-calendars/{calendar_id}", response_model=WasteCalendarSetting, dependencies=[Depends(require_csrf)])
def update_waste_calendar_settings(calendar_id: str, data: WasteCalendarSetting, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    current = accessible_waste_calendar(db, calendar_id, user, manage=True)
    valid_ids = set(db.scalars(select(User.id).where(User.is_active.is_(True))))
    if set(data.visible_to_user_ids) - valid_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Auswahl enthält unbekannte Personen")
    value = data.model_dump(exclude={"id", "owner_user_id", "can_manage", "can_delete", "hidden_for_me", "last_sync_at", "last_result", "last_error"})
    value.update({"id": calendar_id, "owner_user_id": current.get("owner_user_id") or user.id, "hidden_for_user_ids": current.get("hidden_for_user_ids", [])})
    value.update({key: current.get(key) for key in ("last_sync_at", "last_result", "last_error")})
    save_waste_config(db, value)
    audit(db, request, "WASTE_CALENDAR_SETTINGS_CHANGED", user.id, ("waste_calendar", calendar_id), {"name": value["name"], "visibility": value["visible_to_user_ids"]})
    db.commit()
    return waste_calendar_out(value, user)


@router.put("/waste-calendars/{calendar_id}/personal-visibility", response_model=WasteCalendarSetting, dependencies=[Depends(require_csrf)])
def update_waste_calendar_personal_visibility(calendar_id: str, hidden: bool, db: Session = Depends(get_db), user: User = Depends(current_user)):
    value = accessible_waste_calendar(db, calendar_id, user)
    hidden_for = set(value.get("hidden_for_user_ids", []))
    if hidden:
        hidden_for.add(user.id)
    else:
        hidden_for.discard(user.id)
    value["hidden_for_user_ids"] = sorted(hidden_for)
    save_waste_config(db, value)
    db.commit()
    return waste_calendar_out(value, user)


@router.delete("/waste-calendars/{calendar_id}", status_code=204, dependencies=[Depends(require_csrf)])
def remove_waste_calendar(calendar_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    value = accessible_waste_calendar(db, calendar_id, user, manage=True)
    source = db.scalar(select(CalendarSource).where(CalendarSource.key == f"waste-calendar-import-{calendar_id}"))
    if source:
        db.execute(delete(CalendarEvent).where(CalendarEvent.source_id == source.id))
        db.delete(source)
    delete_waste_config(db, calendar_id)
    audit(db, request, "WASTE_CALENDAR_DELETED", user.id, ("waste_calendar", calendar_id), {"name": value.get("name")})
    db.commit()
    return Response(status_code=204)


@router.get("/waste-calendar/awido/options")
async def waste_calendar_awido_options(customer: str = "awld", city: str | None = None, _: User = Depends(admin)):
    try:
        return await awido_options(customer.strip().lower(), city)
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Die AWIDO-Auswahl ist derzeit nicht erreichbar")


@router.post("/waste-calendars/{calendar_id}/sync", dependencies=[Depends(require_csrf)])
async def synchronize_waste_calendar(calendar_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    accessible_waste_calendar(db, calendar_id, user, manage=True)
    try:
        result = await sync_waste_calendar(db, calendar_id)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    audit(db, request, "WASTE_CALENDAR_SYNCED", user.id, ("waste_calendar", calendar_id), {"events": result["imported"]})
    db.commit()
    return result


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
    email = str(data.email).strip().lower() if data.email else ""
    if not person.is_pending and not email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für registrierte Personen ist eine E-Mail-Adresse erforderlich")
    if db.scalar(select(User.id).where(func.lower(User.username) == username.lower(), User.id != person.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Benutzername ist bereits vergeben")
    if email and db.scalar(select(User.id).where(func.lower(User.email) == email, User.id != person.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Diese E-Mail-Adresse ist bereits vergeben")
    person.username = username
    person.display_name = data.display_name.strip()
    person.first_name = data.first_name.strip() if data.first_name else None
    person.last_name = data.last_name.strip() if data.last_name else None
    if person.is_pending:
        invitation = db.scalar(select(Invitation).where(Invitation.user_id == person.id))
        if invitation:
            invitation.email = email or None
        person.email = email or (person.email if person.email.endswith("@familienplan.invalid") else f"pending-{uuid.uuid4().hex}@familienplan.invalid")
    else:
        person.email = email
    person.role = data.role
    if data.color:
        person.color = data.color.upper()
    person.birth_date = data.birth_date
    unknown_types = set(data.allowed_event_types) - EVENT_TYPES
    if unknown_types:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte Terminart")
    person.allowed_event_types = list(dict.fromkeys(data.allowed_event_types))
    active_person_ids = set(db.scalars(select(User.id).where(User.is_active.is_(True))))
    unknown_person_ids = set(data.allowed_person_color_ids) - active_person_ids
    if unknown_person_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte Person in der Farbenfreigabe")
    person.allowed_person_color_ids = list(dict.fromkeys(data.allowed_person_color_ids))
    custom_types = custom_calendar_types(db)
    known_custom_type_ids = {item.get("id") for item in custom_types}
    requested_visible = set(data.visible_custom_event_type_ids) | set(data.editable_custom_event_type_ids)
    requested_editable = set(data.editable_custom_event_type_ids)
    if (requested_visible | requested_editable) - known_custom_type_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte eigene Terminart")
    for item in custom_types:
        visible_ids = set(item.get("visible_to_user_ids", []))
        editable_ids = set(item.get("editable_by_user_ids", []))
        if item.get("id") in requested_visible:
            visible_ids.add(person.id)
        else:
            visible_ids.discard(person.id)
        if item.get("id") in requested_editable:
            editable_ids.add(person.id)
            visible_ids.add(person.id)
        else:
            editable_ids.discard(person.id)
        item["visible_to_user_ids"] = sorted(visible_ids)
        item["editable_by_user_ids"] = sorted(editable_ids)
    upsert_application_setting(db, "custom_calendar_types", custom_types)
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
    audit(db, request, "PERSON_ACCESS_CHANGED", actor.id, ("user", str(person.id)), {"username": person.username, "display_name": person.display_name, "role": data.role.value, "children": list(data.child_permissions), "person_colors": person.allowed_person_color_ids, "visible_custom_types": sorted(requested_visible), "editable_custom_types": sorted(requested_editable)})
    db.commit()
    return PersonAccessOut(user=person, child_permissions=data.child_permissions)


@router.delete("/people/{user_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_person(user_id: int, request: Request, db: Session = Depends(get_db), actor: User = Depends(admin)):
    person = db.get(User, user_id)
    if not person or not person.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person nicht gefunden")
    if person.id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das eigene Administratorkonto kann nicht gelöscht werden")

    linked_records = any((
        db.scalar(select(Child.id).where(Child.default_responsible_user_id == person.id).limit(1)),
        db.scalar(select(CalendarEvent.id).where(CalendarEvent.created_by_id == person.id).limit(1)),
        db.scalar(select(Stay.id).where(or_(Stay.responsible_user_id == person.id, Stay.created_by_id == person.id)).limit(1)),
        db.scalar(select(RecurrenceRule.id).where(RecurrenceRule.responsible_user_id == person.id).limit(1)),
        db.scalar(select(HolidayPlan.id).where(HolidayPlan.created_by_id == person.id).limit(1)),
        db.scalar(select(HolidayPlanSegment.id).where(HolidayPlanSegment.responsible_user_id == person.id).limit(1)),
        db.scalar(select(ChangeRequest.id).where(or_(ChangeRequest.requested_by_id == person.id, ChangeRequest.affected_user_id == person.id)).limit(1)),
        db.scalar(select(Approval.id).where(Approval.user_id == person.id).limit(1)),
        db.scalar(select(Birthday.id).where(Birthday.created_by_id == person.id).limit(1)),
        db.scalar(select(Invitation.id).where(Invitation.created_by_id == person.id).limit(1)),
    ))
    if linked_records:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Diese Person wird bereits in Planungs- oder Kalenderdaten verwendet und kann deshalb nicht gelöscht werden. Ändere zuerst die zugeordneten Daten.",
        )

    display_name = person.display_name
    db.execute(delete(UserSession).where(UserSession.user_id == person.id))
    db.execute(delete(ChildUserPermission).where(ChildUserPermission.user_id == person.id))
    db.execute(delete(Notification).where(Notification.user_id == person.id))
    db.execute(delete(ApiToken).where(ApiToken.user_id == person.id))
    db.execute(delete(Invitation).where(Invitation.user_id == person.id))
    db.execute(update(AuditLog).where(AuditLog.user_id == person.id).values(user_id=None))

    sections = section_access(db)
    sections = {key: [entry for entry in entries if entry != person.id] for key, entries in sections.items()}
    section_row = db.get(ApplicationSetting, "section_access")
    if section_row:
        section_row.value = sections
    for waste_calendar in list_waste_configs(db):
        audience = waste_calendar.get("visible_to_user_ids", [])
        hidden_for = waste_calendar.get("hidden_for_user_ids", [])
        if person.id in audience or person.id in hidden_for or waste_calendar.get("owner_user_id") == person.id:
            waste_calendar["visible_to_user_ids"] = [entry for entry in audience if entry != person.id]
            waste_calendar["hidden_for_user_ids"] = [entry for entry in hidden_for if entry != person.id]
            if waste_calendar.get("owner_user_id") == person.id:
                waste_calendar["owner_user_id"] = actor.id
            save_waste_config(db, waste_calendar)
    for event in db.scalars(select(CalendarEvent).where(cast(CalendarEvent.visible_to_user_ids, JSONB).contains([person.id]))):
        event.visible_to_user_ids = [entry for entry in (event.visible_to_user_ids or []) if entry != person.id]
    for birthday in db.scalars(select(Birthday).where(cast(Birthday.visible_to_user_ids, JSONB).contains([person.id]))):
        birthday.visible_to_user_ids = [entry for entry in (birthday.visible_to_user_ids or []) if entry != person.id]

    db.delete(person)
    audit(db, request, "PERSON_DELETED", actor.id, ("user", str(user_id)), {"display_name": display_name})
    db.commit()
    return Response(status_code=204)


@router.put("/profile", response_model=UserOut, dependencies=[Depends(require_csrf)])
def update_own_profile(data: ProfileUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    user.color = data.color.upper()
    user.birth_date = data.birth_date
    audit(db, request, "OWN_PROFILE_CHANGED", user.id, ("user", str(user.id)), {"color": user.color, "birth_date": data.birth_date.isoformat() if data.birth_date else None})
    db.commit()
    db.refresh(user)
    return user


@router.put("/profile/password", status_code=204, dependencies=[Depends(require_csrf)])
def change_own_password(data: PasswordChange, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das aktuelle Passwort ist nicht korrekt")
    if verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das neue Passwort muss sich vom bisherigen unterscheiden")
    user.password_hash = hash_password(data.password)
    current_session = getattr(request.state, "auth_session", None)
    statement = delete(UserSession).where(UserSession.user_id == user.id)
    if current_session:
        statement = statement.where(UserSession.id != current_session.id)
    db.execute(statement)
    audit(db, request, "PASSWORD_CHANGED", user.id, ("user", str(user.id)))
    db.commit()
    return Response(status_code=204)


@router.post("/invitations", response_model=InvitationOut, status_code=201, dependencies=[Depends(require_csrf)])
def invite(data: InvitationCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    raw = new_token()
    pending_key = uuid.uuid4().hex
    pending_email = str(data.email).lower() if data.email else f"pending-{pending_key}@familienplan.invalid"
    if data.email and db.scalar(select(User.id).where(func.lower(User.email) == pending_email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Diese E-Mail-Adresse ist bereits vergeben")
    person = User(username=f"pending-{pending_key}", display_name=data.display_name.strip(), email=pending_email,
        password_hash=hash_password(new_token()), role=data.role, is_pending=True)
    db.add(person)
    db.flush()
    invitation = Invitation(email=str(data.email).lower() if data.email else None, role=data.role, display_name=data.display_name,
        child_permissions={str(key): value.value for key, value in data.child_permissions.items()}, token_hash=token_hash(raw),
        token_value=raw, user_id=person.id, created_by_id=user.id, expires_at=utcnow() + timedelta(hours=settings.invitation_hours))
    db.add(invitation)
    db.flush()
    for child_id, permission in data.child_permissions.items():
        if not db.get(Child, child_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Kind {child_id} wurde nicht gefunden")
        db.add(ChildUserPermission(child_id=child_id, user_id=person.id, permission=permission))
    invite_url = f"{settings.app_origin}/invite/{raw}"
    if invitation.email and data.send_email:
        # New invitees do not have an active account yet, so enqueue directly by address.
        from app.integrations import mail_config
        from app.models.entities import OutboxMessage
        if not mail_config(db).get("enabled"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Der E-Mail-Versand ist noch nicht aktiviert")
        db.add(OutboxMessage(channel="email", recipient_key=invitation.email,
            event_key=f"invitation:{invitation.id}:{uuid.uuid4().hex}", event_type="invitation.created",
            payload={"subject": "Einladung zu FamilienPlan", "body": f"{user.display_name} hat dich zu FamilienPlan eingeladen.\n\nEinladung annehmen: {invite_url}"}))
    audit(db, request, "INVITATION_CREATED", user.id, ("invitation", str(invitation.id)), {"email": invitation.email, "role": invitation.role.value, "children": list(data.child_permissions)})
    db.commit()
    # Returned once so an admin can deliver it when SMTP is not configured.
    return InvitationOut(id=invitation.id, email=invitation.email, expires_at=invitation.expires_at, invite_url=invite_url, user_id=person.id)


@router.get("/people/{user_id}/invitation", response_model=InvitationOut)
def person_invitation(user_id: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    invitation = db.scalar(select(Invitation).where(Invitation.user_id == user_id, Invitation.used_at.is_(None)))
    if not invitation or not invitation.token_value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keine offene Einladung vorhanden")
    return InvitationOut(id=invitation.id, email=invitation.email, expires_at=invitation.expires_at,
        invite_url=f"{settings.app_origin}/invite/{invitation.token_value}", user_id=user_id, used_at=invitation.used_at)


@router.post("/people/{user_id}/invitation/renew", response_model=InvitationOut, dependencies=[Depends(require_csrf)])
def renew_person_invitation(user_id: int, request: Request, db: Session = Depends(get_db), actor: User = Depends(admin)):
    person = db.get(User, user_id)
    invitation = db.scalar(select(Invitation).where(Invitation.user_id == user_id, Invitation.used_at.is_(None)))
    if not person or not person.is_pending or not invitation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keine offene Einladung vorhanden")
    raw = new_token()
    invitation.token_hash = token_hash(raw)
    invitation.token_value = raw
    invitation.expires_at = utcnow() + timedelta(hours=settings.invitation_hours)
    audit(db, request, "INVITATION_RENEWED", actor.id, ("invitation", str(invitation.id)), {"user_id": user_id})
    db.commit()
    return InvitationOut(id=invitation.id, email=invitation.email, expires_at=invitation.expires_at,
        invite_url=f"{settings.app_origin}/invite/{raw}", user_id=user_id)


@router.post("/people/{user_id}/invitation/send", status_code=202, dependencies=[Depends(require_csrf)])
def send_person_invitation(user_id: int, request: Request, db: Session = Depends(get_db), actor: User = Depends(admin)):
    invitation = db.scalar(select(Invitation).where(Invitation.user_id == user_id, Invitation.used_at.is_(None)))
    if not invitation or not invitation.token_value or not invitation.email:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Für diese Person ist keine versendbare Einladung vorhanden")
    if invitation.expires_at <= utcnow():
        raise HTTPException(status.HTTP_410_GONE, "Der Einladungslink ist abgelaufen. Bitte zuerst einen neuen Link erzeugen")
    from app.integrations import mail_config
    from app.models.entities import OutboxMessage
    if not mail_config(db).get("enabled"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Der E-Mail-Versand ist noch nicht aktiviert")
    invite_url = f"{settings.app_origin}/invite/{invitation.token_value}"
    db.add(OutboxMessage(channel="email", recipient_key=invitation.email,
        event_key=f"invitation:{invitation.id}:{uuid.uuid4().hex}", event_type="invitation.created",
        payload={"subject": "Einladung zu FamilienPlan", "body": f"{actor.display_name} hat dich zu FamilienPlan eingeladen.\n\nEinladung annehmen: {invite_url}"}))
    audit(db, request, "INVITATION_SENT", actor.id, ("invitation", str(invitation.id)), {"user_id": user_id, "email": invitation.email})
    db.commit()
    return {"queued": True, "recipient": invitation.email}


@router.post("/invitations/accept", response_model=SessionOut)
def accept_invite(data: InvitationAccept, request: Request, response: Response, db: Session = Depends(get_db)):
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash(data.token)).with_for_update())
    if not invitation or invitation.used_at or invitation.expires_at <= utcnow():
        raise HTTPException(status.HTTP_410_GONE, "Diese Einladung ist ungültig oder abgelaufen")
    if invitation.email and str(data.email).lower() != invitation.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Die E-Mail-Adresse stimmt nicht mit der Einladung überein")
    if db.scalar(select(User.id).where(func.lower(User.username) == data.username.lower(), User.id != invitation.user_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Benutzername ist bereits vergeben")
    if db.scalar(select(User.id).where(func.lower(User.email) == str(data.email).lower(), User.id != invitation.user_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Diese E-Mail-Adresse ist bereits vergeben")
    user = db.get(User, invitation.user_id) if invitation.user_id else None
    if user:
        user.username = data.username
        user.display_name = data.display_name
        user.email = str(data.email).lower()
        user.first_name = data.first_name
        user.last_name = data.last_name
        user.password_hash = hash_password(data.password)
        user.role = invitation.role
        user.is_pending = False
    else:
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
    invitation.token_value = None
    if not invitation.user_id:
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
    audit(db, request, "CHILD_CREATED", user.id, ("child", str(child.id)), {"name": child.display_name})
    db.commit()
    return child


@router.put("/children/{child_id}", response_model=ChildOut, dependencies=[Depends(require_csrf)])
def update_child(child_id: int, data: ChildUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    child = db.get(Child, child_id)
    if not child or not child.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kind nicht gefunden")
    for key, value in data.model_dump().items():
        setattr(child, key, value)
    audit(db, request, "CHILD_CHANGED", user.id, ("child", str(child.id)), {"name": child.display_name, "changed_values": data.model_dump(mode="json", exclude_unset=True)})
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
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=ZoneInfo(settings.app_timezone)), True
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=utcnow().tzinfo), False
    return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo(settings.app_timezone)), False


def remove_legacy_school_imports(db: Session, child_id: int, current_source_id: int) -> int:
    """Remove school rows from superseded import paths, never user-created events."""
    old_school_source_ids = select(CalendarSource.id).where(
        CalendarSource.kind == "SCHOOL",
        CalendarSource.id != current_source_id,
    )
    legacy_events = db.scalars(select(CalendarEvent).where(
        CalendarEvent.child_id == child_id,
        CalendarEvent.created_by_id.is_(None),
        CalendarEvent.external_id.is_not(None),
        or_(CalendarEvent.category == "SCHOOL", CalendarEvent.event_type == "SCHOOL"),
        or_(
            CalendarEvent.source_id.is_(None),
            CalendarEvent.source_id.in_(old_school_source_ids),
        ),
    ))
    removed = 0
    for event in legacy_events:
        db.delete(event)
        removed += 1
    return removed


def deduplicate_school_candidates(candidates: list[dict]) -> list[dict]:
    """Prefer the shortest copy when a feed publishes overlapping duplicates."""
    accepted: list[dict] = []
    intervals_by_title: dict[str, list[tuple[datetime, datetime]]] = {}
    for candidate in sorted(candidates, key=lambda item: (item["ends_at"] - item["starts_at"], item["order"])):
        title_key = re.sub(r"\s+", " ", candidate["title"].strip()).casefold()
        if any(
            candidate["starts_at"] < other_end and candidate["ends_at"] > other_start
            for other_start, other_end in intervals_by_title.get(title_key, [])
        ):
            continue
        intervals_by_title.setdefault(title_key, []).append((candidate["starts_at"], candidate["ends_at"]))
        accepted.append(candidate)
    return sorted(accepted, key=lambda item: item["order"])


async def synchronize_child_calendar(db: Session, child: Child) -> dict:
    if not child.school_calendar_url:
        return {"imported": 0, "removed": 0, "message": "Für diese Schule wurde keine öffentliche Kalenderquelle erkannt"}
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
    source = db.scalar(select(CalendarSource).where(CalendarSource.key == f"child-{child.id}-school"))
    if not source:
        source = CalendarSource(key=f"child-{child.id}-school", name=child.school or "Schulkalender", kind="SCHOOL", url=url)
        db.add(source); db.flush()
    candidates: list[dict] = []
    for order, block in enumerate(re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text_data, re.S)):
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
        if not school_event_matches_class(fields["SUMMARY"], fields.get("DESCRIPTION"), child.school_class):
            continue
        external_id = fields.get("UID") or hashlib.sha256(f"{fields['SUMMARY']}|{fields['DTSTART']}".encode()).hexdigest()
        candidates.append({
            "order": order, "external_id": external_id, "title": fields["SUMMARY"],
            "description": fields.get("DESCRIPTION"), "starts_at": starts_at,
            "ends_at": ends_at, "all_day": all_day, "url": fields.get("URL"),
        })
    imported = 0
    seen_external_ids: set[str] = set()
    for candidate in deduplicate_school_candidates(candidates):
        external_id = candidate["external_id"]
        seen_external_ids.add(external_id)
        event = db.scalar(select(CalendarEvent).where(CalendarEvent.source_id == source.id, CalendarEvent.external_id == external_id))
        if not event:
            event = CalendarEvent(source_id=source.id, external_id=external_id); db.add(event)
        event.child_id, event.title, event.description = child.id, candidate["title"], candidate["description"]
        event.starts_at, event.ends_at, event.all_day, event.category, event.event_type, event.url = candidate["starts_at"], candidate["ends_at"], candidate["all_day"], "SCHOOL", "SCHOOL", candidate["url"]
        event.raw_data = {
            "calendar_kind": "school",
            "all_day_start": candidate["starts_at"].date().isoformat() if candidate["all_day"] else None,
            "all_day_end_exclusive": candidate["ends_at"].date().isoformat() if candidate["all_day"] else None,
        }
        imported += 1
    removed = remove_legacy_school_imports(db, child.id, source.id)
    for stale in db.scalars(select(CalendarEvent).where(CalendarEvent.source_id == source.id)):
        if stale.external_id not in seen_external_ids:
            db.delete(stale)
            removed += 1
    source.last_sync_at, source.last_result, source.last_error = utcnow(), {"events": imported, "removed": removed}, None
    db.commit()
    return {"imported": imported, "removed": removed, "message": f"{imported} Schultermine übernommen, {removed} veraltete Einträge entfernt"}


@router.post("/children/{child_id}/calendar/sync", dependencies=[Depends(require_csrf)])
async def sync_child_calendar(child_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    child = db.get(Child, child_id)
    if not child or not child.school_calendar_url:
        return {"imported": 0, "message": "Für diese Schule wurde keine öffentliche Kalenderquelle erkannt"}
    result = await synchronize_child_calendar(db, child)
    audit(db, request, "SCHOOL_CALENDAR_SYNCED", user.id, ("child", str(child_id)), {"events": result["imported"], "removed": result["removed"]})
    db.commit()
    return result


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
    if stay.recurrence_exception_rule_id:
        return db.get(RecurrenceRule, stay.recurrence_exception_rule_id)
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


def untouched_stay_ranges(
    original_start: datetime,
    original_end: datetime,
    new_start: datetime,
    new_end: datetime,
    preserve_remainder: bool,
) -> list[tuple[datetime, datetime]]:
    if not preserve_remainder:
        return []
    ranges = []
    if original_start < new_start < original_end:
        ranges.append((original_start, new_start))
    if original_start < new_end < original_end:
        ranges.append((new_end, original_end))
    return ranges


def stay_payload(db: Session, stay: Stay) -> dict:
    responsible = db.get(User, stay.responsible_user_id)
    rule = inferred_recurrence_rule(db, stay)
    interval_match = re.search(r"INTERVAL=(\d+)", rule.rrule) if rule else None
    day_match = re.search(r"BYMONTHDAY=(\d+)", rule.rrule) if rule else None
    return {
        "id": stay.id, "child_id": stay.child_id, "responsible_user_id": stay.responsible_user_id,
        "responsible_display_name": responsible.display_name if responsible else None,
        "starts_at": stay.starts_at, "ends_at": stay.ends_at, "status": stay.status,
        "title": stay.title, "note": stay.note, "created_by_id": stay.created_by_id, "recurrence_rule_id": rule.id if rule else None,
        "recurrence_interval_weeks": int(interval_match.group(1)) if interval_match else (1 if rule else None), "recurrence_frequency": ("MONTHLY" if rule and "FREQ=MONTHLY" in rule.rrule else "WEEKLY"), "recurrence_day_of_month": int(day_match.group(1)) if day_match else None, "recurrence_until": rule.until_at if rule else None,
    }


@router.get("/children/{child_id}/stays", response_model=list[StayOut])
def stays(child_id: int, from_at: datetime | None = None, to_at: datetime | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != Role.ADMIN and "STAY" not in (user.allowed_event_types or []):
        return []
    assert_child_access(db, user, child_id)
    query = select(Stay).where(Stay.child_id == child_id, Stay.status == PlanStatus.CONFIRMED)
    if user.role != Role.ADMIN:
        query = query.where(Stay.responsible_user_id.in_(visible_person_ids(user)))
    if from_at:
        query = query.where(Stay.ends_at > from_at)
    if to_at:
        query = query.where(Stay.starts_at < to_at)
    return [stay_payload(db, item) for item in db.scalars(query.order_by(Stay.starts_at))]


@router.post("/stays", response_model=StayOut, status_code=201, dependencies=[Depends(require_csrf)])
def create_stay(data: StayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if "STAY" not in (user.allowed_event_types or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Die Terminart Betreuung ist für dich nicht freigeschaltet")
    assert_child_access(db, user, data.child_id, edit=True)
    assert_person_visible(db, user, data.responsible_user_id)
    if user.role != Role.ADMIN and data.status == PlanStatus.CONFIRMED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bestätigte Betreuungszeiten erfordern Zustimmung")
    if data.recurrence_interval_weeks and data.recurrence_until:
        duration_minutes = int((data.ends_at - data.starts_at).total_seconds() / 60)
        matching_rule = None
        for candidate in db.scalars(select(RecurrenceRule).where(
            RecurrenceRule.child_id == data.child_id,
            RecurrenceRule.responsible_user_id == data.responsible_user_id,
            RecurrenceRule.duration_minutes == duration_minutes,
        )):
            representative = db.scalar(select(Stay).where(Stay.recurrence_rule_id == candidate.id).order_by(Stay.starts_at).limit(1))
            if representative and ((representative.note or "") != (data.note or "") or (representative.title or "") != (data.title or "")):
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
                        new_stay = Stay(child_id=data.child_id, responsible_user_id=data.responsible_user_id, starts_at=backward_cursor, ends_at=backward_end, status=PlanStatus.CONFIRMED, title=data.title, note=data.note, created_by_id=user.id, recurrence_rule_id=matching_rule.id)
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
                    db.add(Stay(child_id=data.child_id, responsible_user_id=data.responsible_user_id, starts_at=cursor_start, ends_at=cursor_end, status=PlanStatus.CONFIRMED, title=data.title, note=data.note, created_by_id=user.id, recurrence_rule_id=matching_rule.id))
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
        stay = Stay(child_id=data.child_id, responsible_user_id=data.responsible_user_id, starts_at=starts_at, ends_at=ends_at, status=data.status, title=data.title, note=data.note, created_by_id=user.id, recurrence_rule_id=rule.id if rule else None)
        db.add(stay); created.append(stay)
    db.flush()
    audit(db, request, "STAY_SERIES_CREATED" if rule else "STAY_CREATED", user.id, ("stay", str(created[0].id)), {"status": data.status.value, "occurrences": len(created)})
    db.commit()
    return stay_payload(db, created[0])


@router.post("/stays/conflicts", response_model=list[StayOut], dependencies=[Depends(require_csrf)])
def stay_conflicts(data: StayCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assert_child_access(db, user, data.child_id, edit=True)
    assert_person_visible(db, user, data.responsible_user_id)
    occurrences = recurrence_dates(data)
    found: dict[int, Stay] = {}
    for starts_at, ends_at in occurrences:
        for stay in db.scalars(select(Stay).where(
            Stay.child_id == data.child_id, Stay.status == PlanStatus.CONFIRMED,
            Stay.starts_at < ends_at, Stay.ends_at > starts_at,
        )):
            found[stay.id] = stay
    visible_ids = None if user.role == Role.ADMIN else visible_person_ids(user)
    return [
        stay_payload(db, stay)
        for stay in sorted(found.values(), key=lambda item: item.starts_at)
        if visible_ids is None or stay.responsible_user_id in visible_ids
    ]


def stay_request_recipient_id(
    requester_id: int,
    default_responsible_user_id: int | None,
    current_responsible_user_id: int | None = None,
    proposed_responsible_user_id: int | None = None,
) -> int | None:
    """Choose the other person involved in a care request."""
    if current_responsible_user_id and proposed_responsible_user_id and current_responsible_user_id != proposed_responsible_user_id:
        recipient_id = current_responsible_user_id if requester_id == proposed_responsible_user_id else proposed_responsible_user_id
    else:
        responsible_user_id = proposed_responsible_user_id or current_responsible_user_id
        recipient_id = responsible_user_id if responsible_user_id != requester_id else default_responsible_user_id
    return recipient_id if recipient_id and recipient_id != requester_id else None


@router.post("/stay-proposals", response_model=ChangeRequestOut, status_code=201, dependencies=[Depends(require_csrf)])
def propose_new_stay(data: StayCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if "STAY" not in (user.allowed_event_types or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Die Terminart Betreuung ist für dich nicht freigeschaltet")
    assert_child_access(db, user, data.child_id, edit=True)
    assert_person_visible(db, user, data.responsible_user_id)
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
    occurrences = recurrence_dates(data)
    overlapping: dict[int, Stay] = {}
    for starts_at, ends_at in occurrences:
        for stay in db.scalars(select(Stay).where(
            Stay.child_id == data.child_id,
            Stay.status == PlanStatus.CONFIRMED,
            Stay.starts_at < ends_at,
            Stay.ends_at > starts_at,
        )):
            overlapping[stay.id] = stay
    if overlapping:
        if len(occurrences) != 1 or len(overlapping) != 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Für diesen Zeitraum bestehen bereits Betreuungen. Bitte ändere die vorhandenen Einträge einzeln.")
        existing = next(iter(overlapping.values()))
        if existing.responsible_user_id == data.responsible_user_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Für diese Person besteht in diesem Zeitraum bereits eine Betreuung")
        affected_id = stay_request_recipient_id(user.id, child.default_responsible_user_id, existing.responsible_user_id, data.responsible_user_id)
        if not affected_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für diesen Vorschlag gibt es keine andere Person zur Bestätigung")
        proposed = {
            "starts_at": data.starts_at.isoformat(), "ends_at": data.ends_at.isoformat(),
            "responsible_user_id": data.responsible_user_id, "title": data.title, "note": data.note,
            "scope": "occurrence", "preserve_remainder": False,
        }
        item = ChangeRequest(
            object_type="stay", object_id=existing.id, requested_by_id=user.id,
            affected_user_id=affected_id, status=PlanStatus.CHANGE_PROPOSED,
            before_data={"starts_at": existing.starts_at.isoformat(), "ends_at": existing.ends_at.isoformat(), "responsible_user_id": existing.responsible_user_id, "title": existing.title, "note": existing.note},
            proposed_data=proposed,
        )
        db.add(item); db.flush()
        notify(db, affected_id, "STAY_PROPOSAL", "Neue Betreuungsanfrage", f"{user.display_name} schlägt eine Übergabe der Betreuung vor. {change_request_details(db, item)}", item.id)
        audit(db, request, "STAY_CHANGE_PROPOSED", user.id, ("change_request", str(item.id)), {"affected_user_id": affected_id, "scope": "occurrence", "converted_from_create": True})
        db.commit(); db.refresh(item)
        return change_request_payload(db, item, user)

    affected_id = stay_request_recipient_id(user.id, child.default_responsible_user_id, proposed_responsible_user_id=data.responsible_user_id)
    if not affected_id or affected_id == user.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für diesen Vorschlag gibt es keine andere Person zur Bestätigung")
    rule = None
    if data.recurrence_interval_weeks:
        rule = RecurrenceRule(child_id=data.child_id, responsible_user_id=data.responsible_user_id, rrule=f"FREQ={data.recurrence_frequency};INTERVAL={data.recurrence_interval_weeks};BYMONTHDAY={data.recurrence_day_of_month or data.starts_at.day}", starts_at=data.starts_at, duration_minutes=int((data.ends_at-data.starts_at).total_seconds()/60), until_at=data.recurrence_until)
        db.add(rule); db.flush()
    created = []
    for starts_at, ends_at in occurrences:
        stay = Stay(child_id=data.child_id, responsible_user_id=data.responsible_user_id, starts_at=starts_at, ends_at=ends_at, status=PlanStatus.PROPOSED, title=data.title, note=data.note, created_by_id=user.id, recurrence_rule_id=rule.id if rule else None)
        db.add(stay); created.append(stay)
    db.flush()
    item = ChangeRequest(
        object_type="stay", object_id=created[0].id, requested_by_id=user.id,
        affected_user_id=affected_id, status=PlanStatus.PROPOSED, before_data={},
        proposed_data={"action": "CREATE", "stay_ids": [stay.id for stay in created], "starts_at": data.starts_at.isoformat(), "ends_at": data.ends_at.isoformat(), "responsible_user_id": data.responsible_user_id, "title": data.title, "note": data.note, "scope": "series" if rule else "occurrence", "recurrence_interval_weeks": data.recurrence_interval_weeks, "recurrence_until": data.recurrence_until.isoformat() if data.recurrence_until else None},
    )
    db.add(item); db.flush()
    notify(db, affected_id, "STAY_PROPOSAL", "Neue Betreuungsanfrage", f"{user.display_name} schlägt eine neue Betreuungszeit vor.", item.id)
    audit(db, request, "NEW_STAY_PROPOSED", user.id, ("change_request", str(item.id)), {"occurrences": len(created)})
    db.commit(); db.refresh(item)
    return change_request_payload(db, item, user)


@router.put("/stays/{stay_id}", response_model=list[StayOut], dependencies=[Depends(require_csrf)])
def update_stay(stay_id: int, data: StayUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stay = db.get(Stay, stay_id)
    if not stay:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Betreuungszeit nicht gefunden")
    if not getattr(request.state, "approved_change", False):
        assert_child_access(db, user, stay.child_id, edit=True)
        assert_person_visible(db, user, data.responsible_user_id)
    if user.role != Role.ADMIN and stay.status == PlanStatus.CONFIRMED and not getattr(request.state, "approved_change", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bestätigte Betreuungszeiten müssen über eine Änderungsanfrage geändert werden")
    if "title" not in data.model_fields_set:
        data.title = stay.title
    rule = inferred_recurrence_rule(db, stay)
    rule_id = rule.id if rule else None
    if data.scope != "occurrence" and not rule_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Diese Betreuungszeit gehört zu keiner Serie")
    query = select(Stay).where(Stay.id == stay.id)
    if data.scope == "future":
        query = select(Stay).where(((Stay.recurrence_rule_id == rule_id) | (Stay.id == stay.id)), Stay.starts_at >= stay.starts_at)
    elif data.scope == "series":
        query = select(Stay).where(Stay.recurrence_rule_id == rule_id)
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
            title=data.title, note=data.note,
            recurrence_interval_weeks=data.recurrence_interval_weeks,
            recurrence_frequency=recurrence_frequency,
            recurrence_day_of_month=recurrence_day,
            recurrence_until=data.recurrence_until,
        )
        occurrences = recurrence_dates(template)
        excluded_starts = set(db.scalars(select(Stay.recurrence_original_start).where(
            Stay.recurrence_exception_rule_id == rule.id,
            Stay.recurrence_original_start.is_not(None),
        )))
        for target in targets:
            db.delete(target)
        replacements = []
        for starts_at, ends_at in occurrences:
            if starts_at in excluded_starts:
                continue
            replacement = Stay(
                child_id=stay.child_id,
                responsible_user_id=data.responsible_user_id,
                starts_at=starts_at,
                ends_at=ends_at,
                status=stay.status,
                title=data.title, note=data.note,
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
    original_title = stay.title
    original_responsible_user_id, original_note = stay.responsible_user_id, stay.note
    original_status, original_created_by_id = stay.status, stay.created_by_id
    delta_start, delta_end = data.starts_at - stay.starts_at, data.ends_at - stay.ends_at
    for target in targets:
        new_start, new_end = target.starts_at + delta_start, target.ends_at + delta_end
        target.starts_at, target.ends_at = new_start, new_end
        if "title" in data.model_fields_set:
            target.title = data.title
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
        for remainder_start, remainder_end in untouched_stay_ranges(
            original_start, original_end, data.starts_at, data.ends_at, data.preserve_remainder
        ):
            db.add(Stay(
                child_id=stay.child_id,
                responsible_user_id=original_responsible_user_id,
                starts_at=remainder_start,
                ends_at=remainder_end,
                status=original_status,
                title=original_title, note=original_note,
                created_by_id=original_created_by_id,
                recurrence_rule_id=None,
            ))
        # A deliberately changed occurrence is an explicit exception and must
        # never be regenerated from or moved with the parent series.
        stay.recurrence_exception_rule_id = rule.id if rule else None
        stay.recurrence_original_start = original_start if rule else None
        stay.recurrence_rule_id = None
    audit(db, request, "STAY_SERIES_CHANGED" if len(targets) > 1 else "STAY_CHANGED", user.id, ("stay", str(stay.id)), {"scope": data.scope, "affected": len(targets), "child_id": stay.child_id, "responsible_user_id": data.responsible_user_id, "starts_at": data.starts_at.isoformat(), "ends_at": data.ends_at.isoformat(), "title": data.title, "note": data.note})
    db.commit()
    return [stay_payload(db, item) for item in targets]


def stay_scope_targets(db: Session, stay: Stay, scope: str) -> list[Stay]:
    rule = inferred_recurrence_rule(db, stay)
    if scope != "occurrence" and not rule:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Diese Betreuungszeit gehört zu keiner Serie")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Betreuungszeit nicht gefunden")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Betreuungszeit nicht gefunden")
    assert_child_access(db, user, stay.child_id, edit=True)
    child = db.get(Child, stay.child_id)
    affected_id = stay_request_recipient_id(user.id, child.default_responsible_user_id, current_responsible_user_id=stay.responsible_user_id)
    if not affected_id or affected_id == user.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für diese Löschung gibt es keine andere Person zur Bestätigung")
    item = ChangeRequest(
        object_type="stay", object_id=stay.id, requested_by_id=user.id,
        affected_user_id=affected_id, status=PlanStatus.PROPOSED,
        before_data={"starts_at": stay.starts_at.isoformat(), "ends_at": stay.ends_at.isoformat(), "responsible_user_id": stay.responsible_user_id, "title": stay.title, "note": stay.note},
        proposed_data={"action": "DELETE", "scope": scope},
    )
    db.add(item); db.flush()
    notify(db, affected_id, "STAY_DELETE_PROPOSAL", "Betreuungszeit löschen", f"{user.display_name} schlägt vor, eine Betreuungszeit zu löschen.", item.id)
    audit(db, request, "STAY_DELETE_PROPOSED", user.id, ("change_request", str(item.id)), {"scope": scope})
    db.commit(); db.refresh(item)
    return change_request_payload(db, item, user)


def request_calendar_previews(db: Session, item: ChangeRequest, viewer: User) -> list[dict]:
    """Separate visual proposals from confirmed stays; never used by integrations."""
    if item.status not in {PlanStatus.PROPOSED, PlanStatus.CHANGE_PROPOSED} or viewer.id not in {item.requested_by_id, item.affected_user_id}:
        return []
    if item.object_type not in {"stay", "group_plan"}:
        return []
    data = item.proposed_data or {}
    action = data.get("action", "UPDATE")
    stay = db.get(Stay, item.object_id)
    if not stay:
        return []
    entries = []
    if action in {"CREATE", "GROUP_CREATE"}:
        for target in db.scalars(select(Stay).where(Stay.id.in_(data.get("stay_ids", [item.object_id]))).order_by(Stay.starts_at, Stay.id)):
            entries.append((target, target.starts_at, target.ends_at, target.responsible_user_id, target.title, target.note))
    else:
        targets = stay_scope_targets(db, stay, data.get("scope", "occurrence"))
        if action == "DELETE":
            entries = [(x, x.starts_at, x.ends_at, x.responsible_user_id, x.title, x.note) for x in targets]
        else:
            update = StayUpdate.model_validate(data)
            if update.scope == "series" and update.recurrence_interval_weeks:
                template = StayCreate(child_id=stay.child_id, **{**update.model_dump(exclude={"scope", "preserve_remainder"}), "recurrence_frequency": update.recurrence_frequency or "WEEKLY"})
                excluded = set(db.scalars(select(Stay.recurrence_original_start).where(Stay.recurrence_exception_rule_id == stay.recurrence_rule_id)))
                entries = [(stay, start, end, update.responsible_user_id, data.get("title", stay.title), update.note) for start, end in recurrence_dates(template) if start not in excluded]
            else:
                delta_start, delta_end = update.starts_at - stay.starts_at, update.ends_at - stay.ends_at
                entries = [(x, x.starts_at + delta_start, x.ends_at + delta_end, update.responsible_user_id, data.get("title", x.title), update.note) for x in targets]
    result = []
    for index, (target, start, end, person_id, title, note) in enumerate(entries):
        child = db.get(Child, target.child_id)
        person = db.get(User, person_id)
        result.append({"id": f"request:{item.id}:{index}", "starts_at": start, "ends_at": end,
                       "child_id": target.child_id, "title": title or f"{child.display_name if child else 'Kind'} bei {person.display_name if person else 'Person'}",
                       "note": note, "action": action})
    return result


def change_request_payload(db: Session, item: ChangeRequest, viewer: User) -> ChangeRequestOut:
    requester, affected = db.get(User, item.requested_by_id), db.get(User, item.affected_user_id)
    stay = db.get(Stay, item.object_id) if item.object_type == "stay" else None
    child = db.get(Child, stay.child_id) if stay else None
    proposed_data = dict(item.proposed_data or {})
    before_data = dict(item.before_data or {})
    proposed_person_id = proposed_data.get("responsible_user_id")
    previous_person_id = before_data.get("responsible_user_id")
    proposed_person = db.get(User, proposed_person_id) if proposed_person_id else None
    previous_person = db.get(User, previous_person_id) if previous_person_id else None
    viewer_may_see_all = viewer.role == Role.ADMIN or viewer.id == item.affected_user_id
    visible_ids = visible_person_ids(viewer)
    if proposed_person and (viewer_may_see_all or proposed_person.id in visible_ids):
        proposed_data["responsible_user_name"] = proposed_person.display_name
    if previous_person and (viewer_may_see_all or previous_person.id in visible_ids):
        before_data["responsible_user_name"] = previous_person.display_name
    if proposed_data.get("action") == "CREATE" and stay and stay.recurrence_rule_id:
        rule = db.get(RecurrenceRule, stay.recurrence_rule_id)
        if rule:
            match = re.search(r"INTERVAL=(\d+)", rule.rrule)
            proposed_data.setdefault("recurrence_interval_weeks", int(match.group(1)) if match else 1)
            proposed_data.setdefault("recurrence_until", rule.until_at.isoformat() if rule.until_at else None)
    affected_name = affected.display_name if viewer_may_see_all or affected.id in visible_ids else "Andere Betreuungsperson"
    return ChangeRequestOut(calendar_previews=request_calendar_previews(db, item, viewer), id=item.id, object_type=item.object_type, object_id=item.object_id, requested_by_id=item.requested_by_id, requested_by_name=requester.display_name, affected_user_id=item.affected_user_id, affected_user_name=affected_name, status=item.status, proposed_data=proposed_data, before_data=before_data, child_id=child.id if child else None, child_name=child.display_name if child else None, created_at=item.created_at)


def change_request_details(db: Session, item: ChangeRequest) -> str:
    before, proposed = item.before_data or {}, item.proposed_data or {}
    stay = db.get(Stay, item.object_id)
    child = db.get(Child, stay.child_id) if stay else None
    if proposed.get("action") == "GROUP_CREATE":
        return f"{proposed.get('title') or 'Gruppenplanung'} · {len(proposed.get('items') or [])} Zeiträume"
    parts = [child.display_name if child else "Betreuung"]

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
        if "title" in proposed and before.get("title") != proposed.get("title"):
            parts.append(f"Titel: {before.get('title') or '–'} → {proposed.get('title') or '–'}")
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
        responsible = assert_person_visible(db, user, entry.responsible_user_id)
        stay = Stay(
            child_id=entry.child_id,
            responsible_user_id=entry.responsible_user_id,
            starts_at=entry.starts_at,
            ends_at=entry.ends_at,
            status=PlanStatus.CONFIRMED if mode == "direct" else PlanStatus.DRAFT,
            title=entry.name, note=entry.note,
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
    if user.role != Role.ADMIN and "STAY" not in (user.allowed_event_types or []):
        return []
    allowed_child_ids = None
    if user.role != Role.ADMIN:
        allowed_child_ids = list(db.scalars(select(ChildUserPermission.child_id).where(ChildUserPermission.user_id == user.id)))
    query = select(Stay).where(
        Stay.recurrence_rule_id.is_not(None),
        Stay.status == PlanStatus.CONFIRMED,
    ).order_by(Stay.starts_at)
    if user.role != Role.ADMIN:
        query = query.where(
            Stay.child_id.in_(allowed_child_ids),
            Stay.responsible_user_id.in_(visible_person_ids(user)),
        )
    representatives: dict[int, Stay] = {}
    for stay in db.scalars(query):
        representatives.setdefault(stay.recurrence_rule_id, stay)
    return [stay_payload(db, stay) for stay in representatives.values()]


@router.get("/calendar-series", response_model=list[CalendarEventOut])
def calendar_series(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(CalendarEvent).where(
        CalendarEvent.recurrence_group.is_not(None),
        (CalendarEvent.event_type != "PRIVATE")
        | (CalendarEvent.created_by_id == user.id)
        | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]),
    ).order_by(CalendarEvent.starts_at)
    if user.role != Role.ADMIN:
        custom_labels = visible_custom_calendar_labels(db, user)
        allowed_child_ids = list(db.scalars(select(ChildUserPermission.child_id).where(ChildUserPermission.user_id == user.id)))
        query = query.where(
            ((CalendarEvent.child_id.is_(None)) | (CalendarEvent.child_id.in_(allowed_child_ids))),
            ((CalendarEvent.is_private.is_(False)) | (CalendarEvent.created_by_id == user.id) | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id])),
            or_(CalendarEvent.event_type.in_(user.allowed_event_types or []), CalendarEvent.event_type == "PRIVATE", and_(CalendarEvent.event_type == "OTHER", CalendarEvent.custom_type_label.in_(custom_labels))),
        )
    representatives: dict[str, CalendarEvent] = {}
    for event in db.scalars(query):
        representatives.setdefault(event.recurrence_group, event)
    return list(representatives.values())


@router.get("/change-requests", response_model=list[ChangeRequestOut])
def change_requests(db: Session = Depends(get_db), user: User = Depends(current_user), include_closed: bool = False):
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
    query = select(ChangeRequest)
    if not include_closed:
        query = query.where(ChangeRequest.status.in_([PlanStatus.PROPOSED, PlanStatus.CHANGE_PROPOSED]))
    if user.role != Role.ADMIN:
        query = query.where((ChangeRequest.affected_user_id == user.id) | (ChangeRequest.requested_by_id == user.id))
    query = query.order_by(ChangeRequest.created_at.desc())
    if include_closed:
        query = query.limit(100)
    return [change_request_payload(db, item, user) for item in db.scalars(query)]


@router.post("/stays/{stay_id}/proposals", response_model=ChangeRequestOut, status_code=201, dependencies=[Depends(require_csrf)])
def propose_stay_change(stay_id: int, data: StayUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stay = db.get(Stay, stay_id)
    if not stay:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Betreuungszeit nicht gefunden")
    assert_child_access(db, user, stay.child_id, edit=True)
    assert_person_visible(db, user, data.responsible_user_id)
    child = db.get(Child, stay.child_id)
    affected_user_id = stay_request_recipient_id(
        user.id,
        child.default_responsible_user_id if child else None,
        current_responsible_user_id=stay.responsible_user_id,
        proposed_responsible_user_id=data.responsible_user_id,
    )
    affected = db.get(User, affected_user_id) if affected_user_id else None
    if not affected or not affected.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die angefragte Person wurde nicht gefunden")
    if affected.id == user.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Für diese Änderung gibt es keine andere Person zur Bestätigung")
    proposed = data.model_dump(mode="json")
    if "title" not in data.model_fields_set:
        proposed.pop("title")
    item = ChangeRequest(object_type="stay", object_id=stay.id, requested_by_id=user.id, affected_user_id=affected.id, status=PlanStatus.PROPOSED, before_data={"starts_at": stay.starts_at.isoformat(), "ends_at": stay.ends_at.isoformat(), "responsible_user_id": stay.responsible_user_id, "title": stay.title, "note": stay.note}, proposed_data=proposed)
    db.add(item); db.flush()
    notify(db, affected.id, "STAY_PROPOSAL", "Neue Betreuungsanfrage", f"{user.display_name} schlägt eine Änderung vor. {change_request_details(db, item)}", item.id)
    audit(db, request, "STAY_CHANGE_PROPOSED", user.id, ("change_request", str(item.id)), {"affected_user_id": affected.id, "scope": data.scope})
    db.commit(); db.refresh(item)
    return change_request_payload(db, item, user)


@router.post("/change-requests/{change_id}/withdraw", status_code=204, dependencies=[Depends(require_csrf)])
def withdraw_change_request(change_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.scalar(select(ChangeRequest).where(ChangeRequest.id == change_id).with_for_update())
    if not item or item.status not in {PlanStatus.PROPOSED, PlanStatus.CHANGE_PROPOSED}:
        raise HTTPException(404, "Offene Anfrage nicht gefunden")
    if item.requested_by_id != user.id:
        raise HTTPException(403, "Nur die anfragende Person kann diese Anfrage zurückziehen")
    rule_ids = set()
    for stay in db.scalars(select(Stay).where(Stay.id.in_(item.proposed_data.get("stay_ids", [item.object_id])), Stay.status.in_([PlanStatus.DRAFT, PlanStatus.PROPOSED]))):
        if stay.recurrence_rule_id:
            rule_ids.add(stay.recurrence_rule_id)
        db.delete(stay)
    db.flush()
    for rule_id in rule_ids:
        if not db.scalar(select(Stay.id).where(or_(Stay.recurrence_rule_id == rule_id, Stay.recurrence_exception_rule_id == rule_id)).limit(1)):
            rule = db.get(RecurrenceRule, rule_id)
            if rule:
                db.delete(rule)
    item.status = PlanStatus.CANCELLED
    audit(db, request, "STAY_REQUEST_WITHDRAWN", user.id, ("change_request", str(item.id)), {})
    db.commit()
    return Response(status_code=204)


@router.post("/change-requests/{change_id}/decision", response_model=ChangeRequestOut, dependencies=[Depends(require_csrf)])
def decide_change_request(change_id: int, data: ChangeDecision, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.scalar(select(ChangeRequest).where(ChangeRequest.id == change_id).with_for_update())
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
        notify(db, item.requested_by_id, "STAY_APPROVED", "Gruppenplanung bestätigt" if is_group else "Betreuungsanfrage bestätigt", f"{user.display_name} hat deinen Vorschlag bestätigt. {details}{f' · Kommentare: {decision_comment}' if decision_comment else ''}")
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
        notify(db, item.requested_by_id, "STAY_REJECTED", "Gruppenplanung abgelehnt" if item.proposed_data.get("action") == "GROUP_CREATE" else "Betreuungsanfrage abgelehnt", f"{user.display_name} hat den Vorschlag abgelehnt. {details} · Begründung: {decision_comment}")
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
                assert_person_visible(db, user, entry.responsible_user_id)
                stay = Stay(child_id=entry.child_id, responsible_user_id=entry.responsible_user_id, starts_at=entry.starts_at, ends_at=entry.ends_at, status=PlanStatus.DRAFT, title=entry.name, note=entry.note, created_by_id=user.id)
                db.add(stay)
                db.flush()
                new_stay_ids.append(stay.id)
                new_items.append({**entry.model_dump(mode="json"), "stay_id": stay.id, "comment": raw_entry.get("comment")})
            item.object_id = new_stay_ids[0]
            item.proposed_data = {"action": "GROUP_CREATE", "title": counter.get("title") or item.proposed_data.get("title"), "stay_ids": new_stay_ids, "items": new_items}
        elif item.proposed_data.get("action") == "CREATE":
            counter = StayUpdate.model_validate(data.counter_proposal)
            original = db.get(Stay, item.object_id)
            if not original:
                raise HTTPException(409, "Die vorgeschlagene Betreuung ist nicht mehr verfügbar")
            assert_child_access(db, user, original.child_id, edit=True)
            assert_person_visible(db, user, counter.responsible_user_id)
            template = StayCreate(child_id=original.child_id,
                **{**counter.model_dump(exclude={"scope", "preserve_remainder"}), "recurrence_frequency": counter.recurrence_frequency or "WEEKLY"})
            old_ids = item.proposed_data.get("stay_ids", [item.object_id])
            for old in db.scalars(select(Stay).where(Stay.id.in_(old_ids), Stay.id != original.id, Stay.status != PlanStatus.CONFIRMED)):
                db.delete(old)
            rule = db.get(RecurrenceRule, original.recurrence_rule_id) if original.recurrence_rule_id else None
            if counter.recurrence_interval_weeks:
                if not rule:
                    rule = RecurrenceRule(child_id=original.child_id)
                    db.add(rule)
                rule.responsible_user_id = counter.responsible_user_id
                rule.starts_at, rule.until_at = counter.starts_at, counter.recurrence_until
                rule.duration_minutes = int((counter.ends_at - counter.starts_at).total_seconds() / 60)
                rule.rrule = f"FREQ={template.recurrence_frequency};INTERVAL={counter.recurrence_interval_weeks};BYMONTHDAY={counter.recurrence_day_of_month or counter.starts_at.day}"
                db.flush()
            new_ids = []
            for index, (start, end) in enumerate(recurrence_dates(template)):
                target = original if index == 0 else Stay(child_id=original.child_id, created_by_id=original.created_by_id)
                target.starts_at, target.ends_at = start, end
                target.responsible_user_id, target.title, target.note = counter.responsible_user_id, template.title, counter.note
                target.status = PlanStatus.PROPOSED
                target.recurrence_rule_id = rule.id if rule and counter.recurrence_interval_weeks else None
                db.add(target)
                db.flush()
                new_ids.append(target.id)
            if rule and not counter.recurrence_interval_weeks and not db.scalar(select(Stay.id).where(
                or_(Stay.recurrence_rule_id == rule.id, Stay.recurrence_exception_rule_id == rule.id)
            ).limit(1)):
                db.delete(rule)
            item.proposed_data = {**counter.model_dump(mode="json"), "action": "CREATE", "stay_ids": new_ids}
        else:
            item.proposed_data = data.counter_proposal.model_dump(mode="json") if hasattr(data.counter_proposal, "model_dump") else data.counter_proposal
        item.status = PlanStatus.CHANGE_PROPOSED
        notify(db, previous_requester, "STAY_COUNTER", "Gegenvorschlag zur Gruppenplanung" if item.proposed_data.get("action") == "GROUP_CREATE" else "Gegenvorschlag zur Betreuung", f"{user.display_name} hat einen Gegenvorschlag gesendet. {change_request_details(db, item)}{f' · Kommentare: {decision_comment}' if decision_comment else ''}", item.id)
        db.commit()
    db.refresh(item)
    return change_request_payload(db, item, user)


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return list(db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)))


@router.get("/push/config")
def push_config(db: Session = Depends(get_db), user: User = Depends(current_user)):
    public_key = vapid_config(db)["public_key"]
    db.commit()
    return {"public_key": public_key, "subscriptions": db.scalar(select(func.count(PushSubscription.id)).where(PushSubscription.user_id == user.id)) or 0}


@router.post("/push/subscriptions", status_code=201, dependencies=[Depends(require_csrf)])
def save_push_subscription(data: PushSubscriptionCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint))
    if item and item.user_id != user.id:
        item.user_id = user.id
    if not item:
        item = PushSubscription(user_id=user.id, endpoint=data.endpoint, p256dh=data.keys.p256dh, auth=data.keys.auth)
        db.add(item)
    item.p256dh, item.auth = data.keys.p256dh, data.keys.auth
    item.user_agent = (request.headers.get("user-agent") or "")[:500]
    db.commit()
    return {"enabled": True}


@router.delete("/push/subscriptions", status_code=204, dependencies=[Depends(require_csrf)])
def remove_push_subscription(endpoint: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint, PushSubscription.user_id == user.id))
    if item:
        db.delete(item)
        db.commit()
    return Response(status_code=204)


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
    visible_custom_labels: set[str] = set()
    if user.role != Role.ADMIN:
        allowed_child_ids = list(db.scalars(select(ChildUserPermission.child_id).where(ChildUserPermission.user_id == user.id)))
        visible_custom_labels = {
            item["name"] for item in custom_calendar_types(db)
            if user.id in item.get("visible_to_user_ids", []) or user.id in item.get("editable_by_user_ids", [])
        }
    query = select(CalendarEvent).where(
        CalendarEvent.starts_at < to_at,
        CalendarEvent.ends_at > from_at,
        (CalendarEvent.event_type != "PRIVATE")
        | (CalendarEvent.created_by_id == user.id)
        | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]),
    )
    if user.role != Role.ADMIN:
        query = query.where(or_(CalendarEvent.event_type.in_(user.allowed_event_types or []), CalendarEvent.event_type == "PRIVATE", and_(CalendarEvent.event_type == "OTHER", CalendarEvent.custom_type_label.in_(visible_custom_labels))))
        query = query.where((CalendarEvent.is_private.is_(False)) | (CalendarEvent.created_by_id == user.id) | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]))
    if allowed_child_ids is not None:
        query = query.where((CalendarEvent.child_id.is_(None)) | (CalendarEvent.child_id.in_(allowed_child_ids)))
    result = list(db.scalars(query.order_by(CalendarEvent.starts_at)))
    if user.role != Role.ADMIN:
        configured_custom_labels = {item["name"] for item in custom_calendar_types(db)}
        result = [event for event in result if not (
            event.event_type == "OTHER"
            and event.custom_type_label in configured_custom_labels
            and event.custom_type_label not in visible_custom_labels
        )]
    hidden_waste_calendar_ids = {
        item["id"] for item in list_waste_configs(db)
        if user.id in item.get("hidden_for_user_ids", [])
    }
    if hidden_waste_calendar_ids:
        hidden_source_keys = {f"waste-calendar-import-{calendar_id}" for calendar_id in hidden_waste_calendar_ids}
        if "legacy" in hidden_waste_calendar_ids:
            hidden_source_keys.add("waste-calendar-import")
        hidden_source_ids = set(db.scalars(select(CalendarSource.id).where(CalendarSource.key.in_(hidden_source_keys))))
        result = [event for event in result if not (
            event.event_type == "WASTE"
            and (event.source_id in hidden_source_ids or (
                event.raw_data and event.raw_data.get("waste_calendar_id") in hidden_waste_calendar_ids
            ))
        )]
    children_by_id = {
        child.id: child
        for child in db.scalars(select(Child).where(Child.id.in_({event.child_id for event in result if event.child_id})))
    }
    return [
        event for event in result
        if event.event_type != "SCHOOL"
        or event.source_id is None
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
        (CalendarEvent.event_type != "PRIVATE")
        | (CalendarEvent.created_by_id == user.id)
        | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]),
    )
    if user.role != Role.ADMIN:
        visible_custom_labels = visible_custom_calendar_labels(db, user)
        event_query = event_query.where(
            or_(CalendarEvent.event_type.in_(user.allowed_event_types or []), CalendarEvent.event_type == "PRIVATE", and_(CalendarEvent.event_type == "OTHER", CalendarEvent.custom_type_label.in_(visible_custom_labels))),
            (CalendarEvent.is_private.is_(False))
            | (CalendarEvent.created_by_id == user.id)
            | cast(CalendarEvent.visible_to_user_ids, JSONB).contains([user.id]),
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
    search_children_by_id = {
        child.id: child
        for child in db.scalars(select(Child).where(Child.id.in_({event.child_id for event in found_events if event.child_id})))
    }
    found_events = [
        event for event in found_events
        if event.event_type != "SCHOOL"
        or event.source_id is None
        or not event.child_id
        or school_event_matches_class(event.title, event.description, search_children_by_id.get(event.child_id).school_class if search_children_by_id.get(event.child_id) else None)
    ]

    stay_query = (
        select(Stay, Child, User)
        .join(Child, Child.id == Stay.child_id)
        .join(User, User.id == Stay.responsible_user_id)
        .where(
            Stay.status == PlanStatus.CONFIRMED,
            matches(Child.display_name, User.display_name, Stay.title, Stay.note),
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
            "title": stay.title or f"{child.display_name} bei {person.display_name}",
            "subtitle": stay.note or "Betreuung",
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


@router.get("/calendar/{event_id}/attachments", response_model=list[CalendarEventAttachmentOut])
def list_calendar_event_attachments(event_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_event_view(db, user, event_id)
    return list(db.scalars(select(CalendarEventAttachment).where(CalendarEventAttachment.event_id == event_id).order_by(CalendarEventAttachment.created_at)))


@router.post("/calendar/{event_id}/attachments", response_model=CalendarEventAttachmentOut, status_code=201, dependencies=[Depends(require_csrf)])
async def upload_calendar_event_attachment(event_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    event = require_event_view(db, user, event_id)
    if user.role == Role.VIEWER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du darfst keine Dokumente hinzufügen")
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in ATTACHMENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Erlaubt sind PDF-, Bild-, Text- und gängige Textdokumente")
    original_name = Path(file.filename or "Dokument").name.replace("\x00", "")[:255] or "Dokument"
    storage_name = uuid.uuid4().hex
    directory = settings.upload_dir.resolve() / "calendar-attachments"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / storage_name
    size = 0
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > ATTACHMENT_MAX_BYTES:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Die Datei darf höchstens 15 MB groß sein")
                output.write(chunk)
        if size == 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Datei ist leer")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    attachment = CalendarEventAttachment(event_id=event.id, uploaded_by_id=user.id, original_name=original_name, storage_name=storage_name, content_type=content_type, size=size)
    db.add(attachment)
    audit(db, request, "CALENDAR_EVENT_ATTACHMENT_ADDED", user.id, ("calendar_event", str(event.id)), {"filename": original_name, "size": size})
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/calendar/{event_id}/attachments/{attachment_id}/file")
def download_calendar_event_attachment(event_id: int, attachment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_event_view(db, user, event_id)
    attachment = db.scalar(select(CalendarEventAttachment).where(CalendarEventAttachment.id == attachment_id, CalendarEventAttachment.event_id == event_id))
    if not attachment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokument nicht gefunden")
    target = settings.upload_dir.resolve() / "calendar-attachments" / attachment.storage_name
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Datei nicht gefunden")
    return FileResponse(target, media_type=attachment.content_type, filename=attachment.original_name, content_disposition_type="inline")


@router.delete("/calendar/{event_id}/attachments/{attachment_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_calendar_event_attachment(event_id: int, attachment_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_event_view(db, user, event_id)
    if user.role == Role.VIEWER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du darfst keine Dokumente löschen")
    attachment = db.scalar(select(CalendarEventAttachment).where(CalendarEventAttachment.id == attachment_id, CalendarEventAttachment.event_id == event_id))
    if not attachment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokument nicht gefunden")
    storage_name, original_name = attachment.storage_name, attachment.original_name
    db.delete(attachment)
    audit(db, request, "CALENDAR_EVENT_ATTACHMENT_DELETED", user.id, ("calendar_event", str(event_id)), {"filename": original_name})
    db.commit()
    (settings.upload_dir.resolve() / "calendar-attachments" / storage_name).unlink(missing_ok=True)
    return Response(status_code=204)


@router.post("/calendar", response_model=CalendarEventOut, status_code=201, dependencies=[Depends(require_csrf)])
def create_calendar_event(data: CalendarEventCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.event_type == "BIRTHDAY":
        raise HTTPException(422, "Bitte Geburtstage mit Namen und Geburtsdatum über /birthdays anlegen")
    waste_section_allowed = data.event_type == "WASTE" and user.id in section_access(db)["waste_collection"]
    custom_type = custom_calendar_type_for_label(db, data.custom_type_label) if data.event_type == "OTHER" else None
    custom_type_allowed = bool(custom_type and (user.role == Role.ADMIN or user.id in custom_type.get("editable_by_user_ids", [])))
    if user.role == Role.VIEWER and not waste_section_allowed:
        if not custom_type_allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Keine Bearbeitungsberechtigung")
    if data.event_type in CHILDLESS_EVENT_TYPES:
        data.child_id = None
    if data.child_id is not None:
        assert_child_access(db, user, data.child_id, edit=not waste_section_allowed)
    if data.event_type != "PRIVATE" and data.event_type not in (user.allowed_event_types or []) and not waste_section_allowed and not custom_type_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Terminart ist für dich nicht freigeschaltet")
    if custom_type:
        data.color = custom_type["color"]
    values = data.model_dump(exclude={"starts_at", "ends_at", "recurrence_day_of_month"})
    values["visible_to_user_ids"] = normalized_audience(db, user.id, values.get("visible_to_user_ids") or []) if data.event_type == "PRIVATE" else None
    values["is_private"] = data.event_type == "PRIVATE"
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
    audit(db, request, "CALENDAR_EVENT_SERIES_CREATED" if group else "CALENDAR_EVENT_CREATED", user.id, ("calendar_event", str(created[0].id)), {"title": data.title, "event_type": data.event_type, "starts_at": data.starts_at.isoformat(), "ends_at": data.ends_at.isoformat(), "occurrences": len(created)})
    db.commit()
    return created[0]


@router.put("/calendar/{event_id}", response_model=CalendarEventOut, dependencies=[Depends(require_csrf)])
def update_calendar_event(event_id: int, data: CalendarEventCreate, request: Request, scope: str = "occurrence", db: Session = Depends(get_db), user: User = Depends(current_user)):
    if scope not in {"occurrence", "future", "series"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungültiger Änderungsumfang")
    event = db.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    if event.event_type == "PRIVATE" and event.created_by_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    if event.is_private and event.created_by_id != user.id and user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nicht gefunden")
    custom_type = custom_calendar_type_for_label(db, data.custom_type_label) if data.event_type == "OTHER" else None
    custom_type_allowed = bool(custom_type and (user.role == Role.ADMIN or user.id in custom_type.get("editable_by_user_ids", [])))
    if user.role == Role.VIEWER and not custom_type_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Keine Bearbeitungsberechtigung")
    if user.role != Role.ADMIN and event.child_id is not None:
        assert_child_access(db, user, event.child_id, edit=True)
    waste_section_allowed = data.event_type == "WASTE" and user.id in section_access(db)["waste_collection"]
    if data.event_type != "PRIVATE" and data.event_type not in (user.allowed_event_types or []) and not waste_section_allowed and not custom_type_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Terminart ist für dich nicht freigeschaltet")
    if custom_type:
        data.color = custom_type["color"]
    data.visible_to_user_ids = normalized_audience(db, event.created_by_id or user.id, data.visible_to_user_ids or []) if data.event_type == "PRIVATE" else None
    data.is_private = data.event_type == "PRIVATE"
    if data.event_type in CHILDLESS_EVENT_TYPES:
        data.child_id = None
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
        audit(db, request, "CALENDAR_EVENT_SERIES_CHANGED", user.id, ("calendar_event_series", group), {"title": data.title, "event_type": data.event_type, "scope": scope, "starts_at": data.starts_at.isoformat(), "ends_at": data.ends_at.isoformat(), "occurrences": len(replacements)})
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
    audit(db, request, "CALENDAR_EVENT_CHANGED", user.id, ("calendar_event", str(event.id)), {"title": event.title, "event_type": event.event_type, "starts_at": event.starts_at.isoformat(), "ends_at": event.ends_at.isoformat(), "description": event.description})
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
    if event.event_type == "PRIVATE" and event.created_by_id != user.id:
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
    audit(db, request, "CALENDAR_EVENT_SERIES_DELETED" if len(targets) > 1 else "CALENDAR_EVENT_DELETED", user.id, ("calendar_event", str(event_id)), {"title": event.title, "event_type": event.event_type, "starts_at": event.starts_at.isoformat(), "scope": scope, "affected": len(targets)})
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
