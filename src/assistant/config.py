from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_max_tokens: int = 512
    telegram_proxy_url: str = ""
    ai_proxy_url: str = ""
    serpapi_api_key: str = ""
    search_max_results: int = 5
    search_timeout_seconds: float = 35.0
    max_tool_rounds: int = 2
    openai_api_key: str = ""
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_transcription_model: str = "openai/gpt-4o-mini-transcribe"
    transcription_language: str = "ru"
    reminder_timezone: str = "Europe/Moscow"
    database_url: str = (
        "postgresql+asyncpg://assistant:assistant_dev_password@localhost:5433/assistant"
    )
    allowed_telegram_user_ids: str = Field(default="")

    @field_validator("telegram_proxy_url")
    @classmethod
    def normalize_telegram_proxy_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""

        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https", "socks4", "socks4a", "socks5", "socks5h"}:
            raise ValueError(
                "TELEGRAM_PROXY_URL must be a valid proxy URL like 'socks5://proxy-host:1080'"
            )
        if not parsed.hostname:
            raise ValueError(
                "TELEGRAM_PROXY_URL must include a hostname, for example 'socks5://proxy-host:1080'"
            )
        return cleaned

    @field_validator("ai_proxy_url")
    @classmethod
    def normalize_ai_proxy_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""

        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("AI_PROXY_URL must use an http:// or https:// scheme")
        if not parsed.hostname:
            raise ValueError(
                "AI_PROXY_URL must include a hostname, for example 'http://proxy-host:3128'"
            )
        return cleaned

    def allowed_user_ids(self) -> frozenset[int]:
        raw = self.allowed_telegram_user_ids.strip()
        if not raw:
            return frozenset()
        try:
            return frozenset(int(part.strip()) for part in raw.split(",") if part.strip())
        except ValueError as exc:
            raise ValueError(
                "ALLOWED_TELEGRAM_USER_IDS must contain only comma-separated integers"
            ) from exc

    def reminder_timezone_info(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.reminder_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"REMINDER_TIMEZONE must be a valid IANA timezone, got {self.reminder_timezone!r}"
            ) from exc
