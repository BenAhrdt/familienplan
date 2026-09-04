from fastapi.routing import APIRoute
from app.main import app


def test_calendar_deep_link_has_explicit_spa_route():
    route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path == "/calendar"
    )
    assert "GET" in route.methods
    assert route.include_in_schema is False
