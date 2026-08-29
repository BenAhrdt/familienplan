import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_sqlite_is_rejected():
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:///bad.db", secret_key="x" * 32)


def test_postgresql_is_accepted():
    settings = Settings(database_url="postgresql+psycopg://u:p@localhost/db", secret_key="x" * 32)
    assert settings.database_url.startswith("postgresql")

