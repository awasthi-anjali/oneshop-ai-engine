from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None
_cached_key: str = ""


def get_openai_client() -> OpenAI | None:
    global _client, _cached_key
    key = settings.openai_api_key
    if not key:
        _client = None
        _cached_key = ""
        return None
    if _client is None or _cached_key != key:
        _client = OpenAI(api_key=key)
        _cached_key = key
    return _client


def is_ai_enabled() -> bool:
    return settings.ai_enabled and get_openai_client() is not None


def reset_client() -> None:
    """Clear cached client (used on reload)."""
    global _client, _cached_key
    _client = None
    _cached_key = ""
