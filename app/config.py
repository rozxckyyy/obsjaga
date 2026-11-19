from dataclasses import dataclass
from os import getenv
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def database_url() -> str | URL:
    value = getenv("DATABASE_URL", "")
    host = getenv("POSTGRES_HOST")
    if not value and host:
        return URL.create(
            "postgresql+psycopg",
            username=getenv("POSTGRES_USER"),
            password=getenv("POSTGRES_PASSWORD"),
            host=host,
            database=getenv("POSTGRES_DB"),
        )
    if not value.startswith("postgresql+psycopg://"):
        raise RuntimeError("Укажите DATABASE_URL с префиксом postgresql+psycopg://.")
    return value


@dataclass(frozen=True)
class Settings:
    secret_key: str
    https_only: bool
    timezone: ZoneInfo
    developer_contact: str
    developer_phone: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        secret = getenv("SECRET_KEY", "")
        if len(secret) < 32:
            raise RuntimeError("Укажите SECRET_KEY длиной от 32 символов.")
        return cls(
            secret_key=secret,
            https_only=getenv("SESSION_HTTPS_ONLY", "false").lower() == "true",
            timezone=ZoneInfo(getenv("APP_TIMEZONE", "Asia/Yekaterinburg")),
            developer_contact=getenv("DEVELOPER_CONTACT", "").strip(),
            developer_phone=getenv("DEVELOPER_PHONE", "").strip(),
        )
