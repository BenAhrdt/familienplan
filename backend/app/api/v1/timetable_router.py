from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import assert_child_access, current_user, require_csrf
from app.api.v1.integration_router import allowed_children, api_context, need
from app.core.database import get_db
from app.models.entities import Child, ChildUserPermission, Permission, Role, User
from app.timetable import Timetable, timetable_status
from sqlalchemy import select

router = APIRouter()


def timetable_user(request: Request, user: User = Depends(current_user)):
    # Bearer clients must use the integration endpoint, which enforces token scopes.
    if not getattr(request.state, "auth_session", None):
        raise HTTPException(403, "Bitte den Stundenplan über /integrations/v1/children/{id}/timetable abrufen")
    return user



def get_child(db, child_id):
    child = db.get(Child, child_id)
    if not child or not child.is_active:
        raise HTTPException(404, "Kind nicht gefunden")
    return child


def can_edit(db, user, child_id):
    return user.role == Role.ADMIN or db.scalar(select(ChildUserPermission.id).where(
        ChildUserPermission.child_id == child_id, ChildUserPermission.user_id == user.id,
        ChildUserPermission.permission == Permission.EDIT)) is not None


@router.get("/children/{child_id}/timetable")
def get_timetable(child_id: int, on: date | None = None, db: Session = Depends(get_db), user: User = Depends(timetable_user)):
    assert_child_access(db, user, child_id)
    result = timetable_status(get_child(db, child_id), datetime.now(timezone.utc), on)
    result["canEdit"] = can_edit(db, user, child_id)
    return result


@router.put("/children/{child_id}/timetable", dependencies=[Depends(require_csrf)])
def save_timetable(child_id: int, data: Timetable, request: Request, db: Session = Depends(get_db), user: User = Depends(timetable_user)):
    assert_child_access(db, user, child_id, edit=True)
    child = get_child(db, child_id)
    child.timetable = data.model_dump(mode="json")
    from app.api.v1.router import audit
    audit(db, request, "CHILD_TIMETABLE_CHANGED", user.id, ("child", str(child.id)), {"lesson_count": len(data.lessons)})
    db.commit()
    return get_timetable(child_id, db=db, user=user)


@router.get("/integrations/v1/children/{child_id}/timetable")
def integration_timetable(child_id: int, on: date | None = None, context=Depends(api_context), db: Session = Depends(get_db)):
    token, user = context
    need(token, "read:children")
    if child_id not in allowed_children(token, user, db):
        raise HTTPException(403, "Keine Berechtigung für dieses Kind")
    return timetable_status(get_child(db, child_id), datetime.now(timezone.utc), on)
