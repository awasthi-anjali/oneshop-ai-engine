"""Omnichannel helpers — sync messages and continue URLs."""

from urllib.parse import urlparse

from app.config import settings
from app.services.customer_context import build_customer_context
from app.services.session_store import session_store

CHANNEL_LABELS = {"oneshop": "OneShop Web", "oneapp": "OneApp Mobile"}


def resolve_frontend_base(request_origin: str | None = None) -> str:
    if request_origin:
        parsed = urlparse(request_origin)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return settings.frontend_url.rstrip("/")


def build_sync_message(session_id: str, current_channel: str) -> str:
    info = session_store.get_channel_info(session_id)
    cart = session_store.get_cart(session_id)
    if not info["is_cross_channel"]:
        return ""
    other = info.get("other_channel") or ""
    other_label = CHANNEL_LABELS.get(other, other)
    if cart:
        item_label = "item" if len(cart) == 1 else "items"
        return f"Synced from {other_label} — {len(cart)} {item_label} in your cart"
    viewed = session_store.get_viewed(session_id)
    if viewed:
        return f"Continuing from {other_label} — you viewed {viewed[0].name}"
    return f"Welcome back from {other_label}"


def build_continue_urls(session_id: str, base_url: str | None = None) -> dict[str, str]:
    base = (base_url or settings.frontend_url).rstrip("/")
    return {
        "oneshop": f"{base}/?session_id={session_id}",
        "oneapp": f"{base}/app?session_id={session_id}",
    }


def get_omnichannel_context(
    session_id: str,
    current_channel: str,
    base_url: str | None = None,
) -> dict:
    session_store.record_channel(session_id, current_channel)
    ctx = build_customer_context(session_id)
    ch = session_store.get_channel_info(session_id)
    cart = session_store.get_cart(session_id)
    urls = build_continue_urls(session_id, base_url)
    return {
        "session_id": session_id,
        "customer_id": session_store.get_customer_id(session_id),
        "current_channel": current_channel,
        "last_channel": ch["last_channel"],
        "channels_used": ch["channels_used"],
        "is_cross_channel": ch["is_cross_channel"],
        "other_channel": ch["other_channel"],
        "other_channel_label": CHANNEL_LABELS.get(ch["other_channel"] or "", ""),
        "sync_message": build_sync_message(session_id, current_channel),
        "cart_count": len(cart),
        "wishlist_count": len(session_store.get_wishlist(session_id)),
        "viewed_count": len(session_store.get_viewed(session_id)),
        "continue_url_web": urls["oneshop"],
        "continue_url_app": urls["oneapp"],
        "funnel_stage": ctx["funnel_stage"],
    }
