"""Demo checkout identity per persona — name, email, and card prefill."""

from __future__ import annotations

DEFAULT_CHECKOUT_PROFILES: dict[str, dict[str, str]] = {
    "user_001": {
        "full_name": "Anjali",
        "email": "anjali00223@gmail.com",
        "card_number": "4242424242424242",
    },
    "user_011": {
        "full_name": "Dev Patel",
        "email": "dev.patel@techmail.demo",
        "card_number": "5555555555554444",
    },
    "user_021": {
        "full_name": "Morgan Brooks",
        "email": "morgan.brooks@workmail.demo",
        "card_number": "378282246310005",
    },
    "user_031": {
        "full_name": "Greta Lindstrom",
        "email": "greta.lindstrom@seniormail.demo",
        "card_number": "6011111111111117",
    },
    "user_041": {
        "full_name": "Chris Nguyen",
        "email": "chris.nguyen@familymail.demo",
        "card_number": "4000000000009995",
    },
}

VALID_USER_IDS = set(DEFAULT_CHECKOUT_PROFILES.keys())
_overrides: dict[str, dict[str, str]] = {}


def _normalize_user_id(user_id: str) -> str:
    if user_id not in VALID_USER_IDS:
        return "user_001"
    return user_id


def get_checkout_profile(user_id: str) -> dict[str, str]:
    uid = _normalize_user_id(user_id)
    profile = dict(DEFAULT_CHECKOUT_PROFILES[uid])
    profile.update(_overrides.get(uid, {}))
    return profile


def update_checkout_profile(user_id: str, patch: dict[str, str]) -> dict[str, str]:
    uid = _normalize_user_id(user_id)
    current = get_checkout_profile(uid)
    allowed = {"full_name", "email", "card_number"}
    cleaned = {key: value.strip() for key, value in patch.items() if key in allowed and value.strip()}
    if "card_number" in cleaned:
        cleaned["card_number"] = "".join(ch for ch in cleaned["card_number"] if ch.isdigit())
    if cleaned:
        merged = {**_overrides.get(uid, {}), **cleaned}
        _overrides[uid] = merged
        current = {**current, **cleaned}
    return current


def demo_profiles_with_checkout(profiles: list[dict]) -> list[dict]:
    enriched: list[dict] = []
    for profile in profiles:
        uid = profile["user_id"]
        checkout = get_checkout_profile(uid)
        enriched.append({**profile, **checkout})
    return enriched


def reset_checkout_profile_overrides() -> None:
    """Test helper — in-process demo overrides are not durable across requests."""
    _overrides.clear()
