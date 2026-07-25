from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Prefer deployment/process configuration and only fill missing local values.
load_dotenv(_ENV_FILE, override=False)


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
    resend_api_key: str = ""
    resend_from: str = "Ava at OneShop <onboarding@resend.dev>"
    ava_gmail_address: str = ""
    ava_gmail_app_password: str = ""

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_api_key(cls, value: object) -> str:
        if not value or not isinstance(value, str):
            return ""
        return value.strip().strip('"').strip("'")

    @field_validator(
        "resend_api_key",
        "ava_gmail_address",
        "ava_gmail_app_password",
        mode="before",
    )
    @classmethod
    def normalize_email_config(cls, value: object) -> str:
        if not value or not isinstance(value, str):
            return ""
        return value.strip().strip('"').strip("'")

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def resend_enabled(self) -> bool:
        return bool(self.resend_api_key)

    @property
    def ava_gmail_enabled(self) -> bool:
        return bool(self.ava_gmail_address and self.ava_gmail_app_password)


settings = Settings()
