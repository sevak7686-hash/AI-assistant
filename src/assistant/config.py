from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field
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
    openai_api_key: str = ""
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_transcription_model: str = "openai/gpt-4o-mini-transcribe"
    transcription_language: str = "ru"
    reminder_timezone: str = "Europe/Moscow"
    database_url: str = (
        "postgresql+asyncpg://assistant:assistant_dev_password@localhost:5433/assistant"
    )
    allowed_telegram_user_ids: str = Field(default="")

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
