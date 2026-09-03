from app.waste_calendar import _date, _ics_events, _merge_waste_types, _waste_type


def test_awido_ics_events_are_parsed_as_local_all_day_dates():
    content = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:awido-1
DTSTART;VALUE=DATE:20260907
SUMMARY:Bioabfall
END:VEVENT
END:VCALENDAR
"""
    events = _ics_events(content)
    assert events == [{"UID": "awido-1", "DTSTART": "20260907", "SUMMARY": "Bioabfall"}]
    start = _date(events[0]["DTSTART"])
    assert start.isoformat() == "2026-09-07T00:00:00+02:00"


def test_waste_types_are_derived_from_provider_titles():
    assert _waste_type("Bioabfall in Hohenahr") == "bio"
    assert _waste_type("Gelbe Tonne in Hohenahr") == "yellow"
    assert _waste_type("Restabfall in Hohenahr") == "residual"
    assert _waste_type("Altpapier in Hohenahr") == "paper"
    assert _waste_type("Schadstoffmobil") == "hazardous"


def test_detected_waste_types_default_large_containers_to_disabled_and_keep_selection():
    detected = _merge_waste_types([], ["Bioabfall in Hohenahr", "Bioabfall 1.100 in Hohenahr"])
    assert {item["label"]: item["enabled"] for item in detected} == {
        "Bioabfall 1.100 in Hohenahr": False,
        "Bioabfall in Hohenahr": True,
    }

    configured = [{**item, "enabled": item["label"].startswith("Bioabfall 1.100")} for item in detected]
    refreshed = _merge_waste_types(configured, ["Bioabfall in Hohenahr", "Bioabfall 1.100 in Hohenahr"])
    assert {item["label"]: item["enabled"] for item in refreshed} == {
        "Bioabfall 1.100 in Hohenahr": True,
        "Bioabfall in Hohenahr": False,
    }
