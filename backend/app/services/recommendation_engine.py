from app.models.schemas import CustomerIntent, RecommendationItem
from app.services.ai_client import is_ai_enabled
from app.services.ai_intent_service import extract_intent
from app.services.ai_recommendation_service import enhance_with_ai
from app.services.intent_engine import score_product
from app.services.product_catalog import catalog
from app.services.session_store import session_store


def _merge_signals(wishlist: list, cart: list, viewed: list) -> list:
    seen: set[str] = set()
    merged = []
    for p in cart + wishlist + viewed:
        if p.id not in seen:
            seen.add(p.id)
            merged.append(p)
    return merged


def get_recommendations(
    session_id: str,
    limit: int = 6,
) -> tuple[CustomerIntent, list[RecommendationItem], bool]:
    wishlist = session_store.get_wishlist(session_id)
    cart = session_store.get_cart(session_id)
    viewed = session_store.get_viewed(session_id)
    exclude = {p.id for p in wishlist} | {p.id for p in cart}
    signals = _merge_signals(wishlist, cart, viewed)

    intent = extract_intent(session_id)
    ai_powered = is_ai_enabled() and bool(signals)

    if not signals:
        popular = sorted(catalog.all, key=lambda p: p.rating, reverse=True)
        items = [
            RecommendationItem(product=p, score=p.rating, reason="Top rated in catalog")
            for p in popular[:limit]
        ]
        return intent, items, False

    viewed_ids = set(session_store.get_viewed_ids(session_id))
    wishlist_ids = set(session_store.get_wishlist_ids(session_id))
    viewed_only = viewed_ids - {p.id for p in cart} - wishlist_ids

    scored: list[RecommendationItem] = []
    for product in catalog.all:
        if product.id in exclude or not product.in_stock:
            continue
        score, reason = score_product(product, intent, signals, cart, viewed_only)
        if score > 0:
            scored.append(RecommendationItem(product=product, score=score, reason=reason))

    scored.sort(key=lambda r: r.score, reverse=True)

    if ai_powered:
        final = enhance_with_ai(session_id, scored, limit=limit)
        return intent, final, True

    return intent, scored[:limit], False
