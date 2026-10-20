from datetime import datetime, timedelta
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.v1.router import email_login
from app.core.database import Base
from app.core.security import token_hash, utcnow
from app.integrations import email_login_url, ensure_default_calendar_feeds, queue_mail
from app.models.entities import CalendarFeed, EmailLoginToken, OutboxMessage, Role, User


def _user(**kwargs):
    values = {
        "username": "person",
        "display_name": "Person",
        "email": "person@example.com",
        "password_hash": "x",
        "role": Role.VIEWER,
        "allowed_event_types": ["STAY", "SCHOOL", "GENERAL", "BIRTHDAY"],
    }
    values.update(kwargs)
    return User(**values)


def test_default_calendar_feeds_are_created_only_for_visible_categories():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = _user()
        db.add(user)
        db.commit()

        rows = ensure_default_calendar_feeds(db, user)

        assert [row.name for row in rows] == [
            "Betreuung", "Schule", "Allgemein", "Geburtstage", "Ferien / Feiertage", "Privat",
        ]
        assert [row.event_types for row in rows] == [
            ["STAY"], ["SCHOOL"], ["GENERAL"], ["BIRTHDAY"], ["SCHOOL_HOLIDAY"], ["PRIVATE"],
        ]
        assert all(row.token_value for row in rows)
        assert len(list(db.scalars(select(CalendarFeed)))) == len(rows)

        assert len(ensure_default_calendar_feeds(db, user)) == len(rows)
        assert len(list(db.scalars(select(CalendarFeed)))) == len(rows)


def test_notification_mail_contains_calendar_links_and_one_time_login(monkeypatch):
    import app.integrations as integrations

    config = {
        "enabled": True,
        "host": "smtp.example.test",
        "port": 587,
        "username": None,
        "password": None,
        "from_address": "FamilienPlan <noreply@example.test>",
        "app_url": "https://family.example",
        "security": "none",
    }
    monkeypatch.setattr(integrations, "mail_config", lambda _db: config)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = _user()
        db.add(user)
        db.commit()

        queue_mail(db, user.id, "notification:1", "notification.created", "Neue Nachricht", "Bitte prüfen.", "https://family.example/calendar?request=7")
        db.commit()

        outbox = db.scalar(select(OutboxMessage).where(OutboxMessage.event_type == "notification.digest"))
        assert outbox is not None
        assert [item["name"] for item in outbox.payload["calendar_links"]] == [
            "Betreuung", "Schule", "Allgemein", "Geburtstage", "Ferien / Feiertage", "Privat",
        ]
        login_token = db.scalar(select(EmailLoginToken))
        assert login_token is not None
        assert outbox.payload["login_url"].startswith("https://family.example/api/v1/auth/email-login/")
        assert login_token.redirect_path == "/calendar?request=7"

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
        integrations._send_mail(config, user.email, outbox.payload)
        plain = sent[0].get_body(preferencelist=("plain",)).get_content()
        html = sent[0].get_body(preferencelist=("html",)).get_content()
        assert "14 Tage ab Versand gültig" in plain
        assert "14 Tage ab Versand gültig" in html


def test_email_login_is_reusable_for_fourteen_days_and_rejects_external_redirects():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = _user()
        db.add(user)
        db.commit()
        config = {"app_url": "https://family.example"}

        login_url = email_login_url(db, user, "https://evil.example/steal", config)
        raw = urlsplit(login_url).path.rsplit("/", 1)[-1]
        login_token = db.scalar(select(EmailLoginToken).where(EmailLoginToken.token_hash == token_hash(raw)))
        assert login_token.redirect_path == "/calendar"
        assert login_token.expires_at.replace(tzinfo=None) - datetime.now() > timedelta(days=13)
        db.commit()

        request = Request({
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/auth/email-login/{raw}",
            "headers": [],
            "client": ("testclient", 1234),
        })
        response = email_login(raw, request, db)
        assert response.status_code == 303
        assert response.headers["location"] == "/calendar"
        assert "session_token=" in response.headers["set-cookie"]

        second_response = email_login(raw, request, db)
        assert second_response.status_code == 303
        assert second_response.headers["location"] == "/calendar"

        login_token.used_at = utcnow()
        db.commit()
        with pytest.raises(HTTPException) as error:
            email_login(raw, request, db)
        assert error.value.status_code == 410
