from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import token_hash, utcnow
from app.models.entities import ApiToken, ChildUserPermission, Permission, Role, Session as UserSession, User


def current_user(
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    user: User | None = None
    if session_token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(session_token)))
        if session and session.expires_at > utcnow():
            user = session.user
            request.state.auth_session = session
    elif authorization and authorization.startswith("Bearer "):
        api_token = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash(authorization[7:]), ApiToken.revoked_at.is_(None)))
        if api_token:
            api_token.last_used_at = utcnow()
            user = db.get(User, api_token.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Anmeldung erforderlich")
    return user


def require_csrf(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> None:
    session = getattr(request.state, "auth_session", None)
    if not session and session_token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(session_token)))
    if not session or session.expires_at <= utcnow() or not csrf_token or not secrets_compare(session.csrf_token, csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ungültiger CSRF-Schutz")


def secrets_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a, b)


def admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administratorrechte erforderlich")
    return user


def assert_child_access(db: Session, user: User, child_id: int, edit: bool = False) -> None:
    if user.role == Role.ADMIN:
        return
    required = Permission.EDIT if edit else None
    permission = db.scalar(select(ChildUserPermission).where(ChildUserPermission.child_id == child_id, ChildUserPermission.user_id == user.id))
    if not permission or (required and permission.permission != required):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Keine Berechtigung für dieses Kind")
