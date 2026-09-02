from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    allowed_telegram_user_ids: str = Field(default="")

    def allowed_user_ids(self) -> frozenset[int]:
        raw = self.allowed_telegram_user_ids.strip()
        if not raw:
            return frozenset()
        return frozenset(int(part.strip()) for part in raw.split(",") if part.strip())
