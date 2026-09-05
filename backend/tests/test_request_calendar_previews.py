from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.router import (create_planning_group, decide_change_request, propose_new_stay,
    propose_stay_change, propose_stay_deletion, request_calendar_previews, withdraw_change_request)
from app.api.v1.integration_router import integration_events, child_location
from app.core.database import Base
from app.models.entities import ChangeRequest, Child, PlanStatus, Role, Stay, User
from app.schemas import ChangeDecision, GroupPlanningCreate, GroupPlanningItem, StayCreate, StayUpdate


@pytest.fixture
def context():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        people = [User(username=name, display_name=name, email=f'{name}@example.test', password_hash='x', role=Role.ADMIN) for name in ['sender', 'recipient', 'other']]
        db.add_all(people); db.flush()
        child = Child(first_name='Child', display_name='Child', default_responsible_user_id=people[1].id)
        db.add(child); db.commit()
        request = Request({'type':'http', 'method':'POST', 'path':'/stay-proposals', 'headers':[]})
        yield db, people, child, request


def test_proposed_series_visible_only_to_participants_and_excluded_from_calendar_and_location(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    result = propose_new_stay(StayCreate(child_id=child.id, responsible_user_id=sender.id,
        starts_at=start, ends_at=start+timedelta(days=1), title='Wochenende',
        recurrence_interval_weeks=1, recurrence_until=start+timedelta(weeks=2)), request, db, sender)
    item = db.get(ChangeRequest, result.id)
    assert len(result.calendar_previews) == 3
    assert len(request_calendar_previews(db, item, recipient)) == 3
    assert request_calendar_previews(db, item, other) == []
    token = SimpleNamespace(scopes=['read:stays'])
    rows = integration_events(start, start+timedelta(days=30), context=(token, sender), db=db)
    assert all(row['source'] == 'default' for row in rows)
    location = child_location(child.id, at=start-timedelta(days=1), context=(token, sender), db=db)
    assert location['next_change_at'] is None
    assert location['responsible_user_id'] == recipient.id
    decide_change_request(item.id, ChangeDecision(decision='APPROVE'), request, db, recipient)
    assert request_calendar_previews(db, item, sender) == []
    rows = integration_events(start, start+timedelta(days=30), context=(token, sender), db=db)
    assert len([row for row in rows if row['source'] == 'stay']) == 3


def test_change_and_delete_previews_leave_confirmed_stay_untouched_and_withdraw_preserves_it(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    stay = Stay(child_id=child.id, responsible_user_id=recipient.id, starts_at=start,
                ends_at=start+timedelta(days=1), status=PlanStatus.CONFIRMED, title='Bestätigt', created_by_id=recipient.id)
    db.add(stay); db.commit()
    result = propose_stay_change(stay.id, StayUpdate(starts_at=start+timedelta(days=2), ends_at=start+timedelta(days=3), responsible_user_id=sender.id, scope='occurrence', title='Vorgeschlagen'), request, db, sender)
    assert result.calendar_previews[0]['starts_at'] == start+timedelta(days=2)
    assert stay.starts_at == start and stay.title == 'Bestätigt'
    with pytest.raises(HTTPException):
        withdraw_change_request(result.id, request, db, other)
    withdraw_change_request(result.id, request, db, sender)
    assert db.get(Stay, stay.id).status == PlanStatus.CONFIRMED
    assert request_calendar_previews(db, db.get(ChangeRequest, result.id), sender) == []
    deletion = propose_stay_deletion(stay.id, 'occurrence', request, db, sender)
    assert deletion.calendar_previews[0]['action'] == 'DELETE'
    assert deletion.calendar_previews[0]['starts_at'] == start
    decide_change_request(deletion.id, ChangeDecision(decision='REJECT', comment='Bleibt bestehen'), request, db, recipient)
    assert db.get(Stay, stay.id).status == PlanStatus.CONFIRMED


def test_counterproposal_of_new_stay_updates_preview_and_confirms_latest_dates(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    result = propose_new_stay(StayCreate(child_id=child.id, responsible_user_id=sender.id,
        starts_at=start, ends_at=start+timedelta(days=1), title='Erster Vorschlag'), request, db, sender)
    result = decide_change_request(result.id, ChangeDecision(decision='COUNTER', counter_proposal=StayUpdate(
        starts_at=start+timedelta(days=2), ends_at=start+timedelta(days=3), responsible_user_id=sender.id,
        title='Gegenvorschlag', scope='series', recurrence_interval_weeks=1,
        recurrence_until=start+timedelta(days=9))), request, db, recipient)
    assert len(result.calendar_previews) == 2
    assert result.calendar_previews[0]['starts_at'] == start+timedelta(days=2)
    assert all(row['title'] == 'Gegenvorschlag' for row in result.calendar_previews)
    assert all(stay.status == PlanStatus.PROPOSED for stay in db.scalars(select(Stay)))
    decide_change_request(result.id, ChangeDecision(decision='APPROVE'), request, db, sender)
    assert all(stay.status == PlanStatus.CONFIRMED for stay in db.scalars(select(Stay)))


def test_group_previews_cover_each_section_and_withdraw_removes_drafts(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    result = create_planning_group(GroupPlanningCreate(affected_user_id=recipient.id, items=[
        GroupPlanningItem(child_id=child.id, responsible_user_id=sender.id, starts_at=start+timedelta(days=i*3),
            ends_at=start+timedelta(days=i*3+1), name=f'Abschnitt {i}', kind='FERIEN') for i in range(2)
    ]), request, 'proposal', db, sender)
    item = db.get(ChangeRequest, result['request_id'])
    assert len(request_calendar_previews(db, item, sender)) == 2
    assert len(request_calendar_previews(db, item, recipient)) == 2
    withdraw_change_request(item.id, request, db, sender)
    assert list(db.scalars(select(Stay))) == []
    assert item.status == PlanStatus.CANCELLED
    assert request_calendar_previews(db, item, recipient) == []


def test_withdrawn_series_can_be_proposed_again(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    data = StayCreate(child_id=child.id, responsible_user_id=sender.id,
        starts_at=start, ends_at=start+timedelta(days=1), recurrence_interval_weeks=1,
        recurrence_until=start+timedelta(weeks=2))
    result = propose_new_stay(data, request, db, sender)
    withdraw_change_request(result.id, request, db, sender)
    assert len(propose_new_stay(data, request, db, sender).calendar_previews) == 3


def test_series_change_preview_moves_all_occurrences_without_mutating_confirmed_data(context):
    from app.models.entities import RecurrenceRule
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    rule = RecurrenceRule(child_id=child.id, responsible_user_id=recipient.id, rrule='FREQ=WEEKLY;INTERVAL=1',
        starts_at=start, until_at=start+timedelta(weeks=1), duration_minutes=1440)
    db.add(rule); db.flush()
    stays = [Stay(child_id=child.id, responsible_user_id=recipient.id, starts_at=start+timedelta(weeks=i),
        ends_at=start+timedelta(weeks=i, days=1), status=PlanStatus.CONFIRMED, created_by_id=recipient.id, recurrence_rule_id=rule.id) for i in range(2)]
    db.add_all(stays); db.commit()
    result = propose_stay_change(stays[0].id, StayUpdate(starts_at=start+timedelta(days=1),
        ends_at=start+timedelta(days=2), responsible_user_id=sender.id, scope='series'), request, db, sender)
    assert [row['starts_at'] for row in result.calendar_previews] == [start+timedelta(days=1), start+timedelta(days=8)]
    assert stays[0].starts_at == start and stays[1].starts_at == start+timedelta(weeks=1)


def test_history_keeps_closed_requests_without_previews(context):
    from app.api.v1.router import change_requests
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    result = propose_new_stay(StayCreate(child_id=child.id, responsible_user_id=sender.id,
        starts_at=start, ends_at=start+timedelta(days=1)), request, db, sender)
    withdraw_change_request(result.id, request, db, sender)
    assert change_requests(db, sender) == []
    history = change_requests(db, sender, include_closed=True)
    assert len(history) == 1 and history[0].status == PlanStatus.CANCELLED
    assert history[0].calendar_previews == []
    other.role = Role.VIEWER
    assert change_requests(db, other, include_closed=True) == []


def test_counterproposal_can_replace_series_with_one_occurrence_without_leaving_a_rule(context):
    from app.models.entities import RecurrenceRule
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    result = propose_new_stay(StayCreate(child_id=child.id, responsible_user_id=sender.id,
        starts_at=start, ends_at=start+timedelta(days=1), recurrence_interval_weeks=1,
        recurrence_until=start+timedelta(weeks=2)), request, db, sender)
    result = decide_change_request(result.id, ChangeDecision(decision='COUNTER', counter_proposal=StayUpdate(
        starts_at=start, ends_at=start+timedelta(days=1), responsible_user_id=sender.id, scope='occurrence')),
        request, db, recipient)
    assert len(result.calendar_previews) == 1
    assert list(db.scalars(select(RecurrenceRule))) == []
    withdraw_change_request(result.id, request, db, recipient)
    assert list(db.scalars(select(Stay))) == []
