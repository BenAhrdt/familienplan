from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.router import (change_requests, create_planning_group, create_stay, decide_change_request,
    delete_change_request_draft, edit_change_request_draft, propose_new_stay, propose_stay_change,
    propose_stay_deletion, public_decision_page, public_decision_submit, send_change_request,
    request_calendar_previews, resend_change_request, resend_change_requests_batch,
    send_change_requests_batch, withdraw_change_request)
from app.core.security import new_token, token_hash
from app.api.v1.integration_router import integration_events, child_location
from app.core.database import Base
from app.models.entities import ChangeRequest, Child, OutboxMessage, PlanStatus, PublicDecisionToken, Role, Stay, User
from app.schemas import ChangeDecision, ChangeRequestEmailBatch, ChangeRequestEmailResend, DraftChangeRequestUpdate, GroupPlanningCreate, GroupPlanningItem, StayCreate, StayUpdate


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
    send_change_request(item.id, request, db, sender)
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


def test_same_person_overlap_is_merged_when_new_stay_is_approved(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 12, 25, 14, 30)
    existing = Stay(child_id=child.id, responsible_user_id=recipient.id,
                    starts_at=start, ends_at=datetime(2026, 12, 27, 17),
                    status=PlanStatus.CONFIRMED, title='Wochenende', created_by_id=recipient.id)
    db.add(existing); db.commit()

    result = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=recipient.id,
        starts_at=datetime(2026, 12, 26, 10), ends_at=datetime(2026, 12, 31, 14),
        title='Weihnachtsferien',
    ), request, db, sender)
    send_change_request(result.id, request, db, sender)
    decide_change_request(result.id, ChangeDecision(decision='APPROVE'), request, db, recipient)

    confirmed = list(db.scalars(select(Stay).where(Stay.status == PlanStatus.CONFIRMED)))
    assert len(confirmed) == 1
    assert confirmed[0].starts_at == start
    assert confirmed[0].ends_at == datetime(2026, 12, 31, 14)
    assert confirmed[0].title == 'Weihnachtsferien'
    assert db.get(Stay, existing.id).status == PlanStatus.CONFIRMED


def test_same_person_adjacent_direct_stays_are_merged_but_gap_is_preserved(context):
    db, (sender, recipient, other), child, request = context
    first_start = datetime(2026, 12, 25, 14, 30)
    first_end = datetime(2026, 12, 31, 14)
    first = Stay(child_id=child.id, responsible_user_id=recipient.id,
                 starts_at=first_start, ends_at=first_end,
                 status=PlanStatus.CONFIRMED, created_by_id=recipient.id)
    db.add(first); db.commit()

    create_stay(StayCreate(
        child_id=child.id, responsible_user_id=recipient.id,
        starts_at=first_end, ends_at=datetime(2027, 1, 2, 14),
        status=PlanStatus.CONFIRMED,
    ), request, db, sender)
    confirmed = list(db.scalars(select(Stay).where(Stay.status == PlanStatus.CONFIRMED)))
    assert len(confirmed) == 1
    assert confirmed[0].starts_at == first_start
    assert confirmed[0].ends_at == datetime(2027, 1, 2, 14)

    create_stay(StayCreate(
        child_id=child.id, responsible_user_id=recipient.id,
        starts_at=datetime(2027, 1, 3, 14), ends_at=datetime(2027, 1, 10, 17),
        status=PlanStatus.CONFIRMED,
    ), request, db, sender)
    confirmed = list(db.scalars(select(Stay).where(Stay.status == PlanStatus.CONFIRMED).order_by(Stay.starts_at)))
    assert len(confirmed) == 2
    assert [stay.starts_at for stay in confirmed] == [first_start, datetime(2027, 1, 3, 14)]


def test_different_person_overlap_remains_a_handover_conflict(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 12, 25, 14, 30)
    db.add(Stay(child_id=child.id, responsible_user_id=recipient.id,
                starts_at=start, ends_at=start + timedelta(days=2),
                status=PlanStatus.CONFIRMED, created_by_id=recipient.id))
    db.commit()

    result = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=start + timedelta(hours=1), ends_at=start + timedelta(days=3),
    ), request, db, sender)
    assert result.proposed_data['scope'] == 'occurrence'
    assert result.before_data['responsible_user_id'] == recipient.id


def test_parallel_different_person_overlap_keeps_existing_stay(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    existing = Stay(child_id=child.id, responsible_user_id=sender.id,
                    starts_at=start, ends_at=start + timedelta(days=1),
                    status=PlanStatus.CONFIRMED, created_by_id=sender.id)
    db.add(existing); db.commit()

    result = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=other.id,
        starts_at=start, ends_at=start + timedelta(hours=4), title="PMA",
    ), request, db, sender, parallel=True)
    item = db.get(ChangeRequest, result.id)
    assert item.proposed_data["action"] == "CREATE"
    assert item.affected_user_id == other.id
    assert db.get(Stay, existing.id).status == PlanStatus.CONFIRMED
    assert db.get(Stay, item.object_id).status == PlanStatus.DRAFT

    send_change_request(item.id, request, db, sender)
    decide_change_request(item.id, ChangeDecision(decision="APPROVE"), request, db, other)
    assert db.get(Stay, existing.id).status == PlanStatus.CONFIRMED
    assert db.get(Stay, item.object_id).status == PlanStatus.CONFIRMED
    assert db.get(Stay, item.object_id).parallel is True


def test_change_and_delete_previews_leave_confirmed_stay_untouched_and_withdraw_preserves_it(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    stay = Stay(child_id=child.id, responsible_user_id=recipient.id, starts_at=start,
                ends_at=start+timedelta(days=1), status=PlanStatus.CONFIRMED, title='Bestätigt', created_by_id=recipient.id)
    db.add(stay); db.commit()
    result = propose_stay_change(stay.id, StayUpdate(starts_at=start+timedelta(days=2), ends_at=start+timedelta(days=3), responsible_user_id=sender.id, scope='occurrence', title='Vorgeschlagen'), request, db, sender)
    send_change_request(result.id, request, db, sender)
    assert result.calendar_previews[0]['starts_at'] == start+timedelta(days=2)
    assert stay.starts_at == start and stay.title == 'Bestätigt'
    with pytest.raises(HTTPException):
        withdraw_change_request(result.id, request, db, other)
    withdraw_change_request(result.id, request, db, sender)
    assert db.get(Stay, stay.id).status == PlanStatus.CONFIRMED
    assert request_calendar_previews(db, db.get(ChangeRequest, result.id), sender) == []
    deletion = propose_stay_deletion(stay.id, 'occurrence', request, db, sender)
    send_change_request(deletion.id, request, db, sender)
    assert deletion.calendar_previews[0]['action'] == 'DELETE'
    assert deletion.calendar_previews[0]['starts_at'] == start
    decide_change_request(deletion.id, ChangeDecision(decision='REJECT', comment='Bleibt bestehen'), request, db, recipient)
    assert db.get(Stay, stay.id).status == PlanStatus.CONFIRMED


def test_counterproposal_of_new_stay_updates_preview_and_confirms_latest_dates(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    result = propose_new_stay(StayCreate(child_id=child.id, responsible_user_id=sender.id,
        starts_at=start, ends_at=start+timedelta(days=1), title='Erster Vorschlag'), request, db, sender)
    send_change_request(result.id, request, db, sender)
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
    send_change_request(item.id, request, db, sender)
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
    send_change_request(result.id, request, db, sender)
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
    send_change_request(result.id, request, db, sender)
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
    send_change_request(result.id, request, db, sender)
    result = decide_change_request(result.id, ChangeDecision(decision='COUNTER', counter_proposal=StayUpdate(
        starts_at=start, ends_at=start+timedelta(days=1), responsible_user_id=sender.id, scope='occurrence')),
        request, db, recipient)
    assert len(result.calendar_previews) == 1
    assert list(db.scalars(select(RecurrenceRule))) == []
    withdraw_change_request(result.id, request, db, recipient)
    assert list(db.scalars(select(Stay))) == []


def test_draft_is_private_until_sent_and_can_be_edited(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    result = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=start, ends_at=start + timedelta(days=1), title="Erster Entwurf",
    ), request, db, sender)
    assert result.status == PlanStatus.DRAFT
    assert len(request_calendar_previews(db, result and db.get(ChangeRequest, result.id), sender)) == 1
    assert request_calendar_previews(db, db.get(ChangeRequest, result.id), recipient) == []
    assert len(change_requests(db, sender)) == 1
    assert change_requests(db, recipient) == []

    updated = {**result.proposed_data, "starts_at": (start + timedelta(days=2)).isoformat(), "ends_at": (start + timedelta(days=3)).isoformat(), "title": "Korrigierter Entwurf"}
    edited = edit_change_request_draft(result.id, DraftChangeRequestUpdate(proposed_data=updated), request, db, sender)
    assert edited.status == PlanStatus.DRAFT
    assert edited.proposed_data["title"] == "Korrigierter Entwurf"
    draft_stay = db.get(Stay, edited.object_id)
    assert draft_stay.status == PlanStatus.DRAFT
    assert draft_stay.starts_at == start + timedelta(days=2)

    sent = send_change_request(result.id, request, db, sender)
    assert sent.status == PlanStatus.PROPOSED
    assert len(request_calendar_previews(db, db.get(ChangeRequest, result.id), recipient)) == 1


def test_public_email_decision_confirms_request_without_login(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 11, 5)
    result = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=start, ends_at=start + timedelta(days=1), title="E-Mail-Link",
    ), request, db, sender)
    send_change_request(result.id, request, db, sender)

    raw = new_token()
    link = PublicDecisionToken(
        token_hash=token_hash(raw), recipient_user_id=recipient.id,
        change_request_ids=[result.id], decision="APPROVE",
    )
    db.add(link)
    db.commit()

    page = public_decision_page(raw, db)
    assert page.status_code == 200
    assert "Bestätigen" in page.body.decode()

    done = public_decision_submit(raw, request, "Per E-Mail bestätigt", db)
    assert done.status_code == 200
    assert "bestätigt" in done.body.decode()
    assert db.get(ChangeRequest, result.id).status == PlanStatus.CONFIRMED
    assert db.get(PublicDecisionToken, link.id).used_at is not None
    assert public_decision_page(raw, db).status_code == 200
    assert "bereits bestätigt" in public_decision_page(raw, db).body.decode()


def test_public_email_batch_decision_rejects_all_requests(context):
    db, (sender, recipient, other), child, request = context
    first = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2026, 11, 10), ends_at=datetime(2026, 11, 11),
    ), request, db, sender)
    second = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2026, 11, 12), ends_at=datetime(2026, 11, 13),
    ), request, db, sender)
    send_change_request(first.id, request, db, sender)
    send_change_request(second.id, request, db, sender)

    raw = new_token()
    link = PublicDecisionToken(
        token_hash=token_hash(raw), recipient_user_id=recipient.id,
        change_request_ids=[first.id, second.id], decision="REJECT",
    )
    db.add(link)
    db.commit()

    page = public_decision_page(raw, db)
    assert page.status_code == 200
    assert "Folgende Anfragen werden abgelehnt" in page.body.decode()
    assert page.body.decode().count("<li") == 2
    done = public_decision_submit(raw, request, "Die Zeiträume passen nicht", db)
    assert done.status_code == 200
    assert db.get(ChangeRequest, first.id).status == PlanStatus.REJECTED
    assert db.get(ChangeRequest, second.id).status == PlanStatus.REJECTED
    assert db.get(PublicDecisionToken, link.id).used_at is not None


def test_public_email_decides_group_entries_individually(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2027, 1, 10)
    result = create_planning_group(GroupPlanningCreate(affected_user_id=recipient.id, items=[
        GroupPlanningItem(child_id=child.id, responsible_user_id=sender.id, starts_at=start,
            ends_at=start + timedelta(days=1), name="Erster Abschnitt", kind="FERIEN"),
        GroupPlanningItem(child_id=child.id, responsible_user_id=sender.id, starts_at=start + timedelta(days=2),
            ends_at=start + timedelta(days=3), name="Zweiter Abschnitt", kind="FEIERTAG"),
    ]), request, "proposal", db, sender)
    item = db.get(ChangeRequest, result["request_id"])
    send_change_request(item.id, request, db, sender)
    first_stay_id, second_stay_id = item.proposed_data["stay_ids"]

    raw = new_token()
    db.add(PublicDecisionToken(
        token_hash=token_hash(raw), recipient_user_id=recipient.id,
        change_request_ids=[item.id], target_items=[{"request_id": item.id, "item_index": 0}], decision="APPROVE",
    ))
    db.commit()
    public_decision_submit(raw, request, "", db)
    assert db.get(ChangeRequest, item.id).status == PlanStatus.PROPOSED
    assert db.get(Stay, first_stay_id).status == PlanStatus.CONFIRMED
    assert db.get(Stay, second_stay_id).status == PlanStatus.PROPOSED

    raw = new_token()
    db.add(PublicDecisionToken(
        token_hash=token_hash(raw), recipient_user_id=recipient.id,
        change_request_ids=[item.id], target_items=[
            {"request_id": item.id, "item_index": 0},
            {"request_id": item.id, "item_index": 1},
        ], decision="APPROVE",
    ))
    db.commit()
    public_decision_submit(raw, request, "", db)
    assert db.get(ChangeRequest, item.id).status == PlanStatus.CONFIRMED
    assert db.get(Stay, first_stay_id).status == PlanStatus.CONFIRMED
    assert db.get(Stay, second_stay_id).status == PlanStatus.CONFIRMED


def test_notification_digest_contains_per_request_and_batch_decision_links(context, monkeypatch):
    import app.integrations as integrations

    db, (sender, recipient, other), child, request = context
    monkeypatch.setattr(integrations, "mail_config", lambda _db: {
        "enabled": True, "host": "smtp.example.test", "port": 587,
        "username": None, "password": None, "from_address": "FamilienPlan <noreply@example.test>",
        "app_url": "https://family.example", "security": "none",
    })
    first = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2026, 12, 1), ends_at=datetime(2026, 12, 2),
    ), request, db, sender)
    second = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2026, 12, 3), ends_at=datetime(2026, 12, 4),
    ), request, db, sender)
    send_change_request(first.id, request, db, sender)
    send_change_request(second.id, request, db, sender)

    digest = db.scalar(select(OutboxMessage).where(OutboxMessage.event_type == "notification.digest"))
    assert digest is not None
    payload = digest.payload
    assert len(payload["entries"]) == 2
    assert all(len(entry["decision_actions"]) == 1 for entry in payload["entries"])
    assert {action["label"] for action in payload["decision_batch_actions"]} == {"Alle bestätigen", "Alle ablehnen"}
    assert all("/api/v1/public/decision/" in entry["decision_actions"][0]["approve_url"] for entry in payload["entries"])
    assert payload["event_type"] == "notification.digest"
    assert "Angefragt:" in payload["entries"][0]["body"]
    assert "01.12.2026 00:00" in payload["entries"][0]["body"]

    sent = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(integrations.smtplib, "SMTP", FakeSMTP)
    integrations._send_mail({
        "host": "smtp.example.test", "port": 587, "username": None, "password": None,
        "from_address": "FamilienPlan <noreply@example.test>", "security": "none",
    }, recipient.email, payload)
    html = sent[0].get_body(preferencelist=("html",)).get_content()
    assert "Bestätigen" in html
    assert "Ablehnen" in html
    assert "Alle bestätigen" in html
    assert "Alle ablehnen" in html


def test_notification_digest_contains_group_entry_links(context, monkeypatch):
    import app.integrations as integrations

    db, (sender, recipient, other), child, request = context
    monkeypatch.setattr(integrations, "mail_config", lambda _db: {
        "enabled": True, "host": "smtp.example.test", "port": 587,
        "username": None, "password": None, "from_address": "FamilienPlan <noreply@example.test>",
        "app_url": "https://family.example", "security": "none",
    })
    result = create_planning_group(GroupPlanningCreate(affected_user_id=recipient.id, items=[
        GroupPlanningItem(child_id=child.id, responsible_user_id=sender.id, starts_at=datetime(2027, 2, 1),
            ends_at=datetime(2027, 2, 2), name="Ferien", kind="FERIEN"),
        GroupPlanningItem(child_id=child.id, responsible_user_id=sender.id, starts_at=datetime(2027, 2, 3),
            ends_at=datetime(2027, 2, 4), name="Feiertag", kind="FEIERTAG"),
    ]), request, "proposal", db, sender)
    send_change_request(result["request_id"], request, db, sender)

    digest = db.scalar(select(OutboxMessage).where(OutboxMessage.event_type == "notification.digest"))
    actions = digest.payload["entries"][0]["decision_actions"]
    assert len(actions) == 2
    assert {action["item_index"] for action in actions} == {0, 1}
    assert {action["label"] for action in actions} == {"Abschnitt 1: Ferien", "Abschnitt 2: Feiertag"}
    assert {action["label"] for action in digest.payload["decision_batch_actions"]} == {"Alle bestätigen", "Alle ablehnen"}


def test_notification_email_shows_current_and_requested_change(context, monkeypatch):
    import app.integrations as integrations

    db, (sender, recipient, other), child, request = context
    monkeypatch.setattr(integrations, "mail_config", lambda _db: {
        "enabled": True, "host": "smtp.example.test", "port": 587,
        "username": None, "password": None, "from_address": "FamilienPlan <noreply@example.test>",
        "app_url": "https://family.example", "security": "none",
    })
    original = Stay(
        child_id=child.id, responsible_user_id=recipient.id,
        starts_at=datetime(2026, 12, 10), ends_at=datetime(2026, 12, 11),
        status=PlanStatus.CONFIRMED, title="Aktueller Termin", created_by_id=recipient.id,
    )
    db.add(original)
    db.commit()
    result = propose_stay_change(original.id, StayUpdate(
        starts_at=datetime(2026, 12, 12), ends_at=datetime(2026, 12, 13),
        responsible_user_id=sender.id, title="Neuer Termin", note="PMA", scope="occurrence",
    ), request, db, sender)
    send_change_request(result.id, request, db, sender)

    digest = db.scalar(select(OutboxMessage).where(OutboxMessage.event_type == "notification.digest"))
    assert digest is not None
    body = digest.payload["entries"][0]["body"]
    assert "Aktuell:" in body
    assert "Angefragt:" in body
    assert "10.12.2026 00:00" in body
    assert "12.12.2026 00:00" in body
    assert "Person: recipient → sender" in body


def test_aware_request_times_are_localized_and_approval_keeps_the_requested_instants(context, monkeypatch):
    import app.integrations as integrations

    db, (sender, recipient, other), child, request = context
    monkeypatch.setattr(integrations, "mail_config", lambda _db: {
        "enabled": True, "host": "smtp.example.test", "port": 587,
        "username": None, "password": None, "from_address": "FamilienPlan <noreply@example.test>",
        "app_url": "https://family.example", "security": "none",
    })
    original_start = datetime(2026, 10, 23, 14, tzinfo=timezone.utc)
    original_end = datetime(2026, 10, 23, 16, tzinfo=timezone.utc)
    requested_end = datetime(2026, 10, 23, 15, tzinfo=timezone.utc)
    original = Stay(
        child_id=child.id, responsible_user_id=recipient.id,
        starts_at=original_start, ends_at=original_end,
        status=PlanStatus.CONFIRMED, title="Testeintrag 2", created_by_id=recipient.id,
    )
    db.add(original)
    db.commit()

    result = propose_stay_change(original.id, StayUpdate(
        starts_at=original_start, ends_at=requested_end,
        responsible_user_id=recipient.id, title="Testeintrag 2", scope="occurrence",
    ), request, db, sender)
    send_change_request(result.id, request, db, sender)

    digest = db.scalar(select(OutboxMessage).where(OutboxMessage.event_type == "notification.digest"))
    assert digest is not None
    body = digest.payload["entries"][0]["body"]
    assert "23.10.2026 16:00" in body
    assert "23.10.2026 17:00" in body

    decide_change_request(result.id, ChangeDecision(decision="APPROVE"), request, db, recipient)
    confirmed = db.get(Stay, original.id)
    assert confirmed is not None
    assert confirmed.starts_at == original_start
    assert confirmed.ends_at == requested_end


def test_batch_send_resend_and_copy_group_requests_into_one_mail(context, monkeypatch):
    import app.integrations as integrations

    db, (sender, recipient, other), child, request = context
    monkeypatch.setattr(integrations, "mail_config", lambda _db: {
        "enabled": True, "host": "smtp.example.test", "port": 587,
        "username": None, "password": None, "from_address": "FamilienPlan <noreply@example.test>",
        "app_url": "https://family.example", "security": "none",
    })
    first = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2027, 3, 1), ends_at=datetime(2027, 3, 2),
    ), request, db, sender)
    second = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2027, 3, 3), ends_at=datetime(2027, 3, 4),
    ), request, db, sender)
    result = send_change_requests_batch(ChangeRequestEmailBatch(request_ids=[second.id, first.id]), request, db, sender)
    assert result == {"sent": 2, "mail_count": 1}
    digest = db.scalar(select(OutboxMessage).where(OutboxMessage.event_type == "notification.digest"))
    assert digest is not None
    available_at = digest.available_at if digest.available_at.tzinfo else digest.available_at.replace(tzinfo=timezone.utc)
    assert available_at <= datetime.now(timezone.utc) + timedelta(seconds=5)
    assert len(digest.payload["entries"]) == 2
    assert "01.03.2027" in digest.payload["entries"][0]["body"]
    assert "03.03.2027" in digest.payload["entries"][1]["body"]
    assert len(digest.payload["decision_batch_actions"]) == 2
    assert all(len(entry["decision_actions"]) == 1 for entry in digest.payload["entries"])
    initial_copy = db.scalar(select(OutboxMessage).where(
        OutboxMessage.event_type == "notification.resend",
        OutboxMessage.recipient_key == sender.email,
    ))
    assert initial_copy is not None
    assert len(initial_copy.payload["entries"]) == 2
    assert "01.03.2027" in initial_copy.payload["entries"][0]["body"]
    assert "03.03.2027" in initial_copy.payload["entries"][1]["body"]
    assert all(entry["decision_actions"] == [] for entry in initial_copy.payload["entries"])
    assert all("ohne aktive Entscheidungslinks" in entry["body"] for entry in initial_copy.payload["entries"])

    result = resend_change_requests_batch(ChangeRequestEmailBatch(request_ids=[second.id, first.id]), request, db, sender)
    assert result == {"queued": 2, "mail_count": 1, "copy_to_self": False}
    resend = db.scalar(select(OutboxMessage).where(
        OutboxMessage.event_type == "notification.resend",
        OutboxMessage.recipient_key == recipient.email,
    ))
    assert resend is not None
    assert len(resend.payload["entries"]) == 2
    assert "01.03.2027" in resend.payload["entries"][0]["body"]
    assert "03.03.2027" in resend.payload["entries"][1]["body"]
    assert len(resend.payload["decision_batch_actions"]) == 2

    result = resend_change_requests_batch(ChangeRequestEmailBatch(request_ids=[first.id, second.id], copy_to_self=True), request, db, sender)
    assert result == {"queued": 2, "mail_count": 1, "copy_to_self": True}
    copies = list(db.scalars(select(OutboxMessage).where(
        OutboxMessage.event_type == "notification.resend",
        OutboxMessage.recipient_key == sender.email,
    )))
    assert len(copies) == 2
    latest_copy = max(copies, key=lambda item: item.id)
    assert len(latest_copy.payload["entries"]) == 2
    assert all(entry["decision_actions"] == [] for entry in latest_copy.payload["entries"])


def test_open_requests_are_listed_by_earliest_period(context):
    db, (sender, recipient, other), child, request = context
    later = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2027, 5, 5), ends_at=datetime(2027, 5, 9),
    ), request, db, sender)
    earlier = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2027, 2, 8), ends_at=datetime(2027, 2, 9),
    ), request, db, sender)

    listed = change_requests(db, sender)

    assert [item.id for item in listed] == [earlier.id, later.id]


def test_resend_uses_current_request_and_copy_has_no_decision_links(context, monkeypatch):
    import app.api.v1.router as router
    import app.integrations as integrations

    db, (sender, recipient, other), child, request = context
    config = {
        "enabled": True, "host": "smtp.example.test", "port": 587,
        "username": None, "password": None, "from_address": "FamilienPlan <noreply@example.test>",
        "app_url": "https://family.example", "security": "none",
    }
    monkeypatch.setattr(integrations, "mail_config", lambda _db: config)
    monkeypatch.setattr(router, "mail_config", lambda _db: config)
    result = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2026, 12, 1), ends_at=datetime(2026, 12, 2),
    ), request, db, sender)
    send_change_request(result.id, request, db, sender)
    item = db.get(ChangeRequest, result.id)
    item.proposed_data = {**item.proposed_data, "starts_at": datetime(2026, 12, 8).isoformat(), "ends_at": datetime(2026, 12, 9).isoformat()}
    db.flush()

    resend_change_request(result.id, ChangeRequestEmailResend(), request, db, sender)
    active_mail = db.scalar(select(OutboxMessage).where(
        OutboxMessage.event_type == "notification.resend",
        OutboxMessage.recipient_key == recipient.email,
    ))
    assert active_mail is not None
    assert "08.12.2026" in active_mail.payload["body"]
    assert len(active_mail.payload["entries"][0]["decision_actions"]) == 1
    assert "/api/v1/public/decision/" in active_mail.payload["entries"][0]["decision_actions"][0]["approve_url"]
    token_count = len(list(db.scalars(select(PublicDecisionToken))))

    resend_change_request(result.id, ChangeRequestEmailResend(copy_to_self=True), request, db, sender)
    copy_mail = db.scalar(select(OutboxMessage).where(
        OutboxMessage.event_type == "notification.resend",
        OutboxMessage.recipient_key == sender.email,
    ))
    assert copy_mail is not None
    assert copy_mail.payload["entries"][0]["decision_actions"] == []
    assert "ohne aktive Entscheidungslinks" in copy_mail.payload["body"]
    assert len(list(db.scalars(select(PublicDecisionToken)))) == token_count


def test_initial_request_sends_non_actionable_copy_to_requester(context, monkeypatch):
    import app.api.v1.router as router
    import app.integrations as integrations

    db, (sender, recipient, other), child, request = context
    config = {
        "enabled": True, "host": "smtp.example.test", "port": 587,
        "username": None, "password": None, "from_address": "FamilienPlan <noreply@example.test>",
        "app_url": "https://family.example", "security": "none",
    }
    monkeypatch.setattr(integrations, "mail_config", lambda _db: config)
    monkeypatch.setattr(router, "mail_config", lambda _db: config)
    result = propose_new_stay(StayCreate(
        child_id=child.id, responsible_user_id=sender.id,
        starts_at=datetime(2027, 4, 1), ends_at=datetime(2027, 4, 2),
    ), request, db, sender)

    send_change_request(result.id, request, db, sender)

    copy_mail = db.scalar(select(OutboxMessage).where(
        OutboxMessage.event_type == "notification.resend",
        OutboxMessage.recipient_key == sender.email,
    ))
    assert copy_mail is not None
    assert copy_mail.payload["entries"][0]["decision_actions"] == []
    assert "ohne aktive Entscheidungslinks" in copy_mail.payload["body"]


def test_group_draft_can_remove_one_entry_and_delete_the_whole_draft(context):
    db, (sender, recipient, other), child, request = context
    start = datetime(2026, 9, 10)
    result = create_planning_group(GroupPlanningCreate(affected_user_id=recipient.id, items=[
        GroupPlanningItem(child_id=child.id, responsible_user_id=sender.id, starts_at=start,
            ends_at=start + timedelta(days=1), name="Erster Abschnitt", kind="FERIEN"),
        GroupPlanningItem(child_id=child.id, responsible_user_id=sender.id, starts_at=start + timedelta(days=3),
            ends_at=start + timedelta(days=4), name="Zweiter Abschnitt", kind="FEIERTAG"),
    ]), request, "proposal", db, sender)
    item = db.get(ChangeRequest, result["request_id"])
    assert item.status == PlanStatus.DRAFT
    first = item.proposed_data["items"][0]
    edited = edit_change_request_draft(item.id, DraftChangeRequestUpdate(proposed_data={
        **item.proposed_data,
        "items": [first],
    }), request, db, sender)
    assert len(edited.proposed_data["items"]) == 1
    assert len(list(db.scalars(select(Stay)))) == 1
    delete_change_request_draft(item.id, request, db, sender)
    assert db.get(ChangeRequest, item.id) is None
    assert list(db.scalars(select(Stay))) == []
