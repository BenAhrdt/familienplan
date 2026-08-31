from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.router import get_theme, resolved_calendar_colors
from app.core.database import Base
from app.models.entities import ApplicationSetting


def test_black_is_a_valid_calendar_color():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            ApplicationSetting(key="theme", value={
                "primary_color": "#000000", "holiday_color": "#000000",
                "birthday_color": "#000000", "school_color": "#000000",
            }),
            ApplicationSetting(key="calendar_colors_7", value={
                "holiday_color": "#000000", "birthday_color": "#000000",
                "school_color": "#000000", "waste_color": "#000000",
            }),
        ])
        db.flush()

        assert get_theme(db, None).holiday_color == "#000000"
        assert resolved_calendar_colors(db, 7) == {
            "holiday_color": "#000000", "birthday_color": "#000000",
            "school_color": "#000000", "waste_color": "#000000",
        }
