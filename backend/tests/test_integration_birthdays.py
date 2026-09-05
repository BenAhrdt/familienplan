from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.integration_router import integration_events
from app.core.database import Base
from app.models.entities import Birthday, Child, ChildUserPermission, Permission, Role, User


def test_calendar_birthdays_include_visible_children_people_and_custom_entries():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        def person(name, **kwargs):
            return User(username=name, display_name=name, email=f'{name}@example.test',
                        password_hash='x', birth_date=date(2000, 2, 29), **kwargs)
        viewer = person('viewer', role=Role.VIEWER)
        visible = person('visible')
        hidden = person('hidden')
        inactive = person('inactive', is_active=False)
        child = Child(first_name='Child', display_name='Child', birth_date=date(2020, 2, 29))
        other = Child(first_name='Other', display_name='Other', birth_date=date(2020, 2, 29))
        db.add_all([viewer, visible, hidden, inactive, child, other]); db.flush()
        viewer.allowed_person_color_ids = [visible.id, inactive.id]
        db.add(ChildUserPermission(user_id=viewer.id, child_id=child.id, permission=Permission.VIEW))
        db.add_all([
            Birthday(first_name='Custom', display_name='Custom', birth_date=date(1990, 2, 28), created_by_id=viewer.id, is_private=False),
            Birthday(first_name='Private', display_name='Private', birth_date=date(1990, 2, 28), created_by_id=hidden.id, is_private=True),
        ])
        db.commit()
        token = SimpleNamespace(scopes=['read:birthdays'])
        def events(**kwargs):
            return integration_events(datetime(2026, 2, 28, 12), datetime(2026, 3, 1),
                                      context=(token, viewer), db=db, **kwargs)
        rows = events()
        assert {row['title'] for row in rows} == {'viewer', 'visible', 'Child', 'Custom'}
        assert len({row['id'] for row in rows}) == 4
        assert all(row['event_type'] == 'BIRTHDAY' and row['all_day'] for row in rows)
        assert next(row for row in rows if row['source'] == 'child')['age'] == 6
        assert {row['title'] for row in events(child_id=child.id)} == {'viewer', 'visible', 'Child', 'Custom'}
        token.scopes = ['read:birthdays', f'child:{other.id}', 'read:private']
        assert {row['title'] for row in events()} == {'viewer', 'visible', 'Custom'}
        token.scopes = []
        assert events() == []
        token.scopes = ['read:birthdays']
        viewer.allowed_event_types = []
        assert events() == []
        viewer.role = Role.ADMIN
        assert {row['title'] for row in events()} == {'viewer', 'visible', 'hidden', 'Child', 'Other', 'Custom'}
        assert integration_events(datetime(2026, 3, 1), datetime(2026, 3, 2), context=(token, viewer), db=db) == []


def test_children_response_includes_birth_date_or_null_for_permitted_children():
    from fastapi.encoders import jsonable_encoder
    from app.api.v1.integration_router import integration_children

    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        viewer = User(username='viewer', display_name='Viewer', email='viewer@example.test',
                      password_hash='x', role=Role.VIEWER)
        children = [
            Child(first_name='Anna', display_name='Anna', birth_date=date(2020, 2, 29)),
            Child(first_name='Ben', display_name='Ben'),
            Child(first_name='Hidden', display_name='Hidden', birth_date=date(2019, 1, 1)),
        ]
        db.add_all([viewer, *children]); db.flush()
        for child in children[:2]:
            db.add(ChildUserPermission(user_id=viewer.id, child_id=child.id, permission=Permission.VIEW))
        db.commit()
        token = SimpleNamespace(scopes=['read:children'])
        result = jsonable_encoder(integration_children(context=(token, viewer), db=db))
        assert [(row['name'], row['birth_date']) for row in result] == [
            ('Anna', '2020-02-29'), ('Ben', None),
        ]
