from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Load .env before Settings so the key is always picked up from disk
load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: str = "none"
    shopassist_intent_model: str = "gpt-5.6-luna"
    openai_timeout_seconds: float = 8.0
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    frontend_url: str = "http://localhost:5173"
    recommendation_db_path: str = str(
        Path(__file__).resolve().parent.parent / "data" / "recommendations.sqlite3"
    )
    ordering_enabled: bool = True
    demo_payment_enabled: bool = True

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_api_key(cls, value: object) -> str:
        if not value or not isinstance(value, str):
            return ""
        return value.strip().strip('"').strip("'")

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
