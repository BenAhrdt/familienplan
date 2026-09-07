from datetime import datetime, timezone, date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.entities import Child, User, Role, ChildUserPermission, Permission, CalendarEvent
from app.timetable import Timetable, timetable_status
from app.timetable_import import parse_tsv, analyze_upload
from app.api.v1.timetable_router import get_timetable, save_timetable, integration_timetable


def plan():
    return Timetable(lessons=[
        {"weekday":0,"start":"08:00","end":"08:45","subject":"Mathematik"},
        {"weekday":0,"start":"08:50","end":"09:35","subject":"Deutsch"},
    ])


def child_with_plan(value=None):
    return SimpleNamespace(id=7,display_name="Rika",timetable=(value or plan()).model_dump(mode="json"))


@pytest.mark.parametrize("clock,expected", [("05:59","before_school"),("06:00","lesson"),("06:44","lesson"),("06:45","break"),("06:49","break"),("06:50","lesson"),("07:35","finished")])
def test_exact_boundaries_in_berlin_summer(clock, expected):
    result = timetable_status(child_with_plan(),datetime.fromisoformat(f"2026-09-07T{clock}:00+00:00"))
    assert result["status"] == expected
    assert len(result["dailySchedule"]) == 2
    assert (result["currentLesson"] is not None) == (expected == "lesson")


def test_winter_timezone_and_status_independent_of_selected_date():
    result = timetable_status(child_with_plan(),datetime(2026,1,5,7,15,tzinfo=timezone.utc),date(2026,1,6))
    assert result["status"] == "lesson"
    assert result["dailySchedule"] == []
    assert result["statusDate"] == "2026-01-05"
    assert result["date"] == "2026-01-06"


def test_missing_empty_weekend_days_off_and_expired():
    now = datetime(2026,9,7,6,15,tzinfo=timezone.utc)
    child = child_with_plan(); child.timetable = None
    assert timetable_status(child,now)["status"] == "not_configured"
    assert timetable_status(child_with_plan(Timetable()),now)["status"] == "no_school"
    assert timetable_status(child_with_plan(),datetime(2026,9,6,6,tzinfo=timezone.utc))["status"] == "no_school"
    p = plan(); p.days_off = [now.date()]
    result = timetable_status(child_with_plan(p),now)
    assert result["status"] == "no_school" and result["currentLesson"] is None
    p = plan(); p.valid_until = date(2026,9,6)
    assert timetable_status(child_with_plan(p),now)["status"] == "outside_validity"


@pytest.mark.parametrize("change", [{"start":"09:00","end":"08:45"},{"subject":"  "},{"weekday":7},{"start":"25:00"}])
def test_invalid_lessons(change):
    lesson = plan().lessons[0].model_dump(); lesson.update(change)
    with pytest.raises(ValidationError): Timetable(lessons=[lesson])


def test_overlaps_and_timezone_validation():
    lessons = [x.model_dump() for x in plan().lessons]; lessons[1]["start"] = "08:44"
    with pytest.raises(ValidationError): Timetable(lessons=lessons)
    with pytest.raises(ValidationError): Timetable(timezone="Not/AZone")
    with pytest.raises(ValidationError): Timetable(valid_from="2026-10-01",valid_until="2026-09-01")


def test_persistence_access_api_scope_and_no_calendar_events(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        editor = User(username="editor",email="editor@example.test",display_name="Editor",password_hash="x",role=Role.EDITOR)
        viewer = User(username="viewer",email="viewer@example.test",display_name="Viewer",password_hash="x",role=Role.VIEWER)
        child = Child(first_name="Rika",display_name="Rika")
        db.add_all([editor,viewer,child]);db.flush()
        db.add_all([ChildUserPermission(user_id=editor.id,child_id=child.id,permission=Permission.EDIT),ChildUserPermission(user_id=viewer.id,child_id=child.id,permission=Permission.VIEW)])
        db.commit()
        monkeypatch.setattr("app.api.v1.router.audit",lambda *args,**kwargs:None)
        result = save_timetable(child.id,plan(),SimpleNamespace(),db,editor)
        assert result["configured"] and result["canEdit"]
        db.expire_all()
        assert len(get_timetable(child.id,db=db,user=viewer)["weeklySchedule"]) == 2
        assert not get_timetable(child.id,db=db,user=viewer)["canEdit"]
        with pytest.raises(HTTPException) as exc: save_timetable(child.id,plan(),SimpleNamespace(),db,viewer)
        assert exc.value.status_code == 403
        token = SimpleNamespace(scopes=["read:children",f"child:{child.id}"])
        assert integration_timetable(child.id,context=(token,viewer),db=db)["childId"] == child.id
        for scopes in [[],["read:children","child:999"]]:
            with pytest.raises(HTTPException) as exc: integration_timetable(child.id,context=(SimpleNamespace(scopes=scopes),viewer),db=db)
            assert exc.value.status_code == 403
        assert db.scalar(select(func.count()).select_from(CalendarEvent)) == 0
        child.is_active = False; db.commit()
        with pytest.raises(HTTPException): get_timetable(child.id,db=db,user=editor)


def test_ocr_table_coordinates_and_pause():
    words = [(200,20,"Montag"),(400,20,"Dienstag"),(20,80,"08:00-08:45"),(200,80,"Mathematik"),(400,80,"Deutsch"),(20,130,"08:45-08:50"),(200,130,"Pause"),(20,180,"08:50-09:35"),(200,180,"Sport")]
    tsv = "level\tleft\ttop\twidth\theight\ttext\n" + "\n".join(f"5\t{x}\t{y}\t80\t16\t{text}" for x,y,text in words)
    lessons, text = parse_tsv(tsv)
    assert [(x["weekday"],x["subject"],x["start"]) for x in lessons] == [(0,"Mathematik","08:00"),(1,"Deutsch","08:00"),(0,"Sport","08:50")]
    assert "Pause" in text
    assert parse_tsv("level\tleft\ttop\twidth\theight\ttext\n5\t0\t0\t10\t10\tHallo")[0] == []


def test_upload_requires_real_file_and_explains_missing_tools(monkeypatch):
    with pytest.raises(ValueError): analyze_upload(b"not an image")
    monkeypatch.setattr("app.timetable_import.shutil.which",lambda _:None)
    with pytest.raises(RuntimeError,match="Serverpakete"): analyze_upload(b"%PDF-1.7")


def test_session_endpoint_rejects_unscoped_bearer():
    from app.api.v1.timetable_router import timetable_user
    with pytest.raises(HTTPException) as exc:
        timetable_user(SimpleNamespace(state=SimpleNamespace()),SimpleNamespace())
    assert exc.value.status_code == 403


def test_upload_pipeline_returns_draft_and_removes_temporary_files(monkeypatch):
    from pathlib import Path
    from app import timetable_import
    paths = []
    monkeypatch.setattr(timetable_import.shutil,"which",lambda name:f"/usr/bin/{name}")
    def run(args,**kwargs):
        source = Path(args[1]); paths.append(source)
        assert source.exists()
        return SimpleNamespace(stdout=b"level\tleft\ttop\twidth\theight\ttext\n5\t0\t0\t10\t10\tMathematik")
    monkeypatch.setattr(timetable_import.subprocess,"run",run)
    result = analyze_upload(b"\x89PNG\r\n\x1a\nfixture")
    assert result["lessons"] == [] and "Mathematik" in result["extractedText"]
    assert all(not path.exists() for path in paths)


def test_pdf_page_limit_before_rasterizing(monkeypatch):
    from app import timetable_import
    monkeypatch.setattr(timetable_import.shutil,"which",lambda name:f"/usr/bin/{name}")
    calls = []
    def run(args,**kwargs):
        calls.append(args[0]);return SimpleNamespace(stdout=b"Pages:          4\n")
    monkeypatch.setattr(timetable_import.subprocess,"run",run)
    with pytest.raises(ValueError,match="3 PDF-Seiten"): analyze_upload(b"%PDF-1.7")
    assert calls == ["pdfinfo"]
