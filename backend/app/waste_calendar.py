import hashlib
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utcnow
from app.models.entities import ApplicationSetting, CalendarEvent, CalendarSource

AWIDO_BASE = "https://awido.cubefour.de"
SETTING_KEY = "waste_calendar"
SOURCE_KEY = "waste-calendar-import"
settings = get_settings()


def get_waste_config(db: Session) -> dict:
    row = db.get(ApplicationSetting, SETTING_KEY)
    return row.value if row else {
        "enabled": False, "provider": "AWIDO", "customer": "awld",
        "city": "Hohenahr", "street": "Ahrdt", "calendar_url": "",
        "visible_to_user_ids": [], "last_sync_at": None, "last_result": None,
        "last_error": None,
    }


def save_waste_config(db: Session, value: dict) -> None:
    row = db.get(ApplicationSetting, SETTING_KEY)
    if row:
        row.value = value
    else:
        db.add(ApplicationSetting(key=SETTING_KEY, value=value))


async def _json(client: httpx.AsyncClient, path: str, params: dict | None = None):
    response = await client.get(f"{AWIDO_BASE}{path}", params=params)
    response.raise_for_status()
    return response.json()


async def awido_options(customer: str, city: str | None = None) -> list[dict]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": "FamilienPlan/0.1"}) as client:
        places = await _json(client, f"/WebServices/Awido.Service.svc/secure/getPlaces/client={customer}")
        if not city:
            return places
        place = next((item for item in places if item["value"].strip().casefold() == city.strip().casefold()), None)
        if not place:
            return []
        return await _json(client, f"/WebServices/Awido.Service.svc/secure/getGroupedStreets/{place['key']}", {"client": customer})


async def _awido_oid(client: httpx.AsyncClient, customer: str, city: str, street: str) -> str:
    places = await _json(client, f"/WebServices/Awido.Service.svc/secure/getPlaces/client={customer}")
    place = next((item for item in places if item["value"].strip().casefold() == city.strip().casefold()), None)
    if not place:
        raise ValueError(f"Ort „{city}“ wurde bei AWIDO nicht gefunden")
    streets = await _json(client, f"/WebServices/Awido.Service.svc/secure/getGroupedStreets/{place['key']}", {"client": customer})
    if not street and len(streets) == 1:
        return streets[0]["key"]
    district = next((item for item in streets if item["value"].strip().casefold() == street.strip().casefold()), None)
    if not district:
        raise ValueError(f"Ortsteil oder Straße „{street}“ wurde bei AWIDO nicht gefunden")
    return district["key"]


def _ics_events(content: str) -> list[dict]:
    content = re.sub(r"\r?\n[ \t]", "", content)
    result = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, re.S):
        fields = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.split(";", 1)[0]] = value.replace("\\,", ",").replace("\\n", "\n")
        if fields.get("DTSTART") and fields.get("SUMMARY"):
            result.append(fields)
    return result


def _date(value: str) -> datetime:
    raw = value.strip()[:8]
    return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=ZoneInfo(settings.app_timezone))


async def sync_waste_calendar(db: Session) -> dict:
    config = dict(get_waste_config(db))
    if not config.get("enabled"):
        return {"imported": 0, "message": "Der automatische Abfallkalender ist deaktiviert"}
    provider = config.get("provider", "AWIDO")
    source = db.scalar(select(CalendarSource).where(CalendarSource.key == SOURCE_KEY))
    if not source:
        source = CalendarSource(key=SOURCE_KEY, name="Automatischer Abfallkalender", kind="WASTE", is_active=True)
        db.add(source)
        db.flush()
    try:
        texts: list[str] = []
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "FamilienPlan/0.1", "Accept": "text/calendar"}) as client:
            if provider == "AWIDO":
                customer = str(config.get("customer") or "").strip().lower()
                oid = await _awido_oid(client, customer, str(config.get("city") or ""), str(config.get("street") or ""))
                for year in (datetime.now().year, datetime.now().year + 1):
                    response = await client.get(f"{AWIDO_BASE}/Customer/{customer}/KalenderICS.aspx", params={"oid": oid, "jahr": year, "fraktionen": "", "reminder": "-1.17:00"})
                    response.raise_for_status()
                    if "BEGIN:VCALENDAR" in response.text:
                        texts.append(response.text)
                source.url = f"{AWIDO_BASE}/Customer/{customer}/v2/Calendar2.aspx"
            else:
                url = str(config.get("calendar_url") or "").replace("webcal://", "https://")
                if not url.startswith(("http://", "https://")):
                    raise ValueError("Bitte eine gültige iCal-/WebCal-Adresse eintragen")
                response = await client.get(url)
                response.raise_for_status()
                texts.append(response.text)
                source.url = url
        audience = [int(item) for item in config.get("visible_to_user_ids", [])]
        imported = 0
        for fields in [item for text in texts for item in _ics_events(text)]:
            starts_at = _date(fields["DTSTART"])
            title = fields["SUMMARY"].strip()
            external_id = fields.get("UID") or hashlib.sha256(f"{title}|{starts_at.date()}".encode()).hexdigest()
            # Some providers reuse a UID across years; date keeps the imported occurrence unique.
            external_id = f"{external_id}:{starts_at.date().isoformat()}"
            event = db.scalar(select(CalendarEvent).where(CalendarEvent.source_id == source.id, CalendarEvent.external_id == external_id))
            if not event:
                event = CalendarEvent(source_id=source.id, external_id=external_id)
                db.add(event)
            event.title = title
            event.description = fields.get("DESCRIPTION") or "Automatisch aus dem Abfallkalender importiert"
            event.starts_at, event.ends_at, event.all_day = starts_at, starts_at + timedelta(days=1), True
            event.category, event.event_type, event.color = "FAMILY", "WASTE", "#5C8B58"
            # An empty selection means “nur Administratoren”, never public.
            event.visible_to_user_ids = audience
            event.is_private = True
            event.raw_data = {"provider": provider, "location": fields.get("LOCATION")}
            imported += 1
        now = utcnow()
        result = {"events": imported, "years": [datetime.now().year, datetime.now().year + 1]}
        source.last_sync_at, source.last_result, source.last_error = now, result, None
        config.update({"last_sync_at": now.isoformat(), "last_result": result, "last_error": None})
        save_waste_config(db, config)
        db.commit()
        return {"imported": imported, "message": f"{imported} Abfuhrtermine synchronisiert"}
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        message = str(exc) or "Der Abfallkalender konnte nicht geladen werden"
        source.last_sync_at, source.last_error = utcnow(), message
        config.update({"last_sync_at": utcnow().isoformat(), "last_error": message})
        save_waste_config(db, config)
        db.commit()
        raise RuntimeError(message) from exc
