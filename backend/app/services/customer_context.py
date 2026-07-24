from app.models.schemas import Product
from app.services.conversation_store import conversation_store
from app.services.session_store import session_store


def get_funnel_stage(session_id: str) -> str:
    cart = session_store.get_cart_ids(session_id)
    wishlist = session_store.get_wishlist_ids(session_id)
    viewed = session_store.get_viewed_ids(session_id)

    if cart:
        return "cart"
    if wishlist:
        return "wishlisted"
    if viewed:
        return "browsing"
    return "new"


def build_customer_context(session_id: str) -> dict:
    wishlist = session_store.get_wishlist(session_id)
    cart = session_store.get_cart(session_id)
    viewed = session_store.get_viewed(session_id)
    chat_snippets = conversation_store.get_history_snippets(session_id)

    def summarize(products: list[Product]) -> list[dict]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category.value,
                "brand": p.brand,
                "price": p.price,
                "tags": p.tags,
            }
            for p in products
        ]

    return {
        "funnel_stage": get_funnel_stage(session_id),
        "wishlist": summarize(wishlist),
        "cart": summarize(cart),
        "viewed_products": summarize(viewed),
        "recent_chat": chat_snippets,
        **session_store.get_channel_info(session_id),
    }


def context_as_text(session_id: str) -> str:
    ctx = build_customer_context(session_id)
    lines = [f"Funnel stage: {ctx['funnel_stage']}"]

    if ctx["cart"]:
        lines.append("Cart: " + ", ".join(p["name"] for p in ctx["cart"]))
    if ctx["wishlist"]:
        lines.append("Wishlist: " + ", ".join(p["name"] for p in ctx["wishlist"]))
    if ctx["viewed_products"]:
        lines.append("Recently viewed: " + ", ".join(p["name"] for p in ctx["viewed_products"]))
    if ctx["recent_chat"]:
        lines.append("Recent chat: " + " | ".join(ctx["recent_chat"][-3:]))

    return "\n".join(lines)
