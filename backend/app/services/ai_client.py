from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def get_openai_client() -> OpenAI | None:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def is_ai_enabled() -> bool:
    return get_openai_client() is not None
