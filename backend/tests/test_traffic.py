import asyncio

from app.api.v1.router import _google_duration_seconds, _traffic_direction, _traffic_direction_placeholder


class Person:
    def __init__(self, person_id: int, name: str, address: str):
        self.id = person_id
        self.display_name = name
        self.address = address


def test_google_duration_seconds_accepts_fractional_seconds():
    assert _google_duration_seconds("635.4s") == 635
    assert _google_duration_seconds(None) == 0
    assert _google_duration_seconds("invalid") == 0


def test_traffic_placeholder_contains_safe_maps_link():
    result = _traffic_direction_placeholder(
        Person(1, "Ben", "Am Hang 1, 12345 Test"),
        Person(2, "Friederike", "Neue Straße 2, 54321 Ziel"),
    )

    assert result["origin_name"] == "Ben"
    assert result["destination_name"] == "Friederike"
    assert result["available"] is False
    assert "Am+Hang+1%2C+12345+Test" in result["maps_url"]
    assert "Neue+Stra%C3%9Fe+2%2C+54321+Ziel" in result["maps_url"]


def test_traffic_direction_calculates_current_delay():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"routes": [{"duration": "2040s", "staticDuration": "1440s", "distanceMeters": 18000}]}

    class Client:
        async def post(self, *args, **kwargs):
            return Response()

    result = asyncio.run(_traffic_direction(
        Client(),
        Person(1, "Ben", "Startstraße 1"),
        Person(2, "Friederike", "Zielstraße 2"),
    ))

    assert result["available"] is True
    assert result["duration_minutes"] == 34
    assert result["usual_duration_minutes"] == 24
    assert result["delay_minutes"] == 10
