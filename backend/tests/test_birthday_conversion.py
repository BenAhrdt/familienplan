from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.router import convert_calendar_birthday, create_birthday, create_calendar_event
from app.api.v1.integration_router import integration_events
from app.core.database import Base
from app.models.entities import Birthday, CalendarEvent, CalendarEventAttachment, Role, User
from app.schemas import BirthdayCreate, CalendarEventCreate


def test_conversion_replaces_legacy_series_with_annual_birthday_and_full_api_name():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    request = Request({'type':'http', 'method':'POST', 'path':'/calendar/1/birthday', 'headers':[]})
    with Session(engine, expire_on_commit=False) as db:
        admin = User(username='admin', display_name='Admin', email='admin@example.test', password_hash='x', role=Role.ADMIN)
        db.add(admin); db.flush()
        events = [CalendarEvent(title='Tom', description='Alte Notiz', event_type='BIRTHDAY',
                   starts_at=datetime(year, 9, 11), ends_at=datetime(year, 9, 12),
                   recurrence_group='legacy', created_by_id=admin.id) for year in [2026, 2027]]
        db.add_all(events); db.commit()
        data = BirthdayCreate(first_name='Tom', last_name='Grywnow', display_name='Tom', birth_date=date(2011, 9, 11))
        birthday = convert_calendar_birthday(events[0].id, data, request, db, admin)
        assert list(db.scalars(select(CalendarEvent))) == []
        assert len(list(db.scalars(select(Birthday)))) == 1
        token = SimpleNamespace(scopes=['read:birthdays', 'read:private'])
        for year in [2026, 2027]:
            rows = integration_events(datetime(year, 9, 1), datetime(year, 10, 1), context=(token, admin), db=db)
            assert len(rows) == 1
            row = rows[0]
            assert row['id'] == birthday.id
            assert row['title'] == row['display_name'] == 'Tom'
            assert row['first_name'] == 'Tom' and row['last_name'] == 'Grywnow'
            assert row['full_name'] == 'Tom Grywnow'
            assert row['birth_date'] == date(2011, 9, 11)
            assert row['age'] == year - 2011 and row['all_day']


def test_calendar_writer_can_create_birthdays_and_plain_calendar_birthdays_are_rejected():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    request = Request({'type':'http', 'method':'POST', 'path':'/birthdays', 'headers':[]})
    with Session(engine) as db:
        user = User(username='writer', display_name='Writer', email='writer@example.test', password_hash='x', role=Role.EDITOR, allowed_event_types=['BIRTHDAY'])
        db.add(user); db.commit()
        data = BirthdayCreate(first_name='Tom', last_name='Grywnow', display_name='Tom', birth_date=date(2011, 9, 11))
        assert create_birthday(data, request, db, user).display_name == 'Tom'
        with pytest.raises(HTTPException) as error:
            create_calendar_event(CalendarEventCreate(title='Tom', event_type='BIRTHDAY', starts_at=datetime(2026, 9, 11), ends_at=datetime(2026, 9, 12)), request, db, user)
        assert error.value.status_code == 422
        user.role = Role.VIEWER
        with pytest.raises(HTTPException) as error:
            create_birthday(data, request, db, user)
        assert error.value.status_code == 403


def test_conversion_does_not_discard_documents_or_allow_another_owner():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    request = Request({'type':'http', 'method':'POST', 'path':'/calendar/1/birthday', 'headers':[]})
    with Session(engine) as db:
        owner = User(username='owner', display_name='Owner', email='owner@example.test', password_hash='x', role=Role.EDITOR)
        other = User(username='other', display_name='Other', email='other@example.test', password_hash='x', role=Role.EDITOR)
        db.add_all([owner, other]); db.flush()
        event = CalendarEvent(title='Tom', event_type='BIRTHDAY', starts_at=datetime(2026, 9, 11),
            ends_at=datetime(2026, 9, 12), created_by_id=owner.id)
        db.add(event); db.flush()
        attachment = CalendarEventAttachment(event_id=event.id, original_name='Notiz.pdf', storage_name='test-document', content_type='application/pdf', size=10)
        db.add(attachment); db.commit()
        data = BirthdayCreate(first_name='Tom', last_name='Grywnow', display_name='Tom', birth_date=date(2011, 9, 11))
        with pytest.raises(HTTPException) as error:
            convert_calendar_birthday(event.id, data, request, db, other)
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            convert_calendar_birthday(event.id, data, request, db, owner)
        assert error.value.status_code == 422
        assert db.get(CalendarEventAttachment, attachment.id) is not None
        assert db.get(CalendarEvent, event.id) is not None
        assert list(db.scalars(select(Birthday))) == []
