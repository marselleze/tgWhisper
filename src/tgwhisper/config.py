from datetime import time
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    openai_api_key: str
    openai_text_model: str = "gpt-5-mini"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    database_path: Path = Path("data/tgwhisper.sqlite3")
    default_timezone: str = "Europe/Moscow"
    default_digest_time: time = time(8, 0)

    @field_validator("telegram_bot_token", "openai_api_key")
    @classmethod
    def reject_placeholders(cls, value: str) -> str:
        if not value or value == "replace-me":
            raise ValueError("credential is not configured")
        return value
