from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "FamilienPlan"
    app_env: str = "development"
    app_origin: str = "http://localhost:5173"
    app_timezone: str = "Europe/Berlin"
    database_url: str
    secret_key: str = Field(min_length=32)
    session_cookie_secure: bool = False
    session_hours: int = 12
    remember_session_days: int = 30
    invitation_hours: int = 72
    upload_dir: Path = Path("./uploads")
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "FamilienPlan <familienplan@example.de>"
    smtp_starttls: bool = True
    github_repository: str | None = None

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("FamilienPlan requires PostgreSQL; SQLite is not supported")
        return value

    @field_validator("upload_dir")
    @classmethod
    def resolve_upload_dir(cls, value: Path) -> Path:
        if value.is_absolute():
            return value
        # Services run from backend/, while uploads live at the project root.
        return (Path(__file__).resolve().parents[3] / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
