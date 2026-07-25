from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.catalog_retrieval import semantic_retrieve_with_meta
from app.services.interaction_store import InteractionStore, interaction_store
from app.services.product_catalog import catalog
from app.services.session_store import session_store


SCORE_WEIGHTS = {
    "semantic": 0.22,
    "brand_affinity": 0.22,
    "category_affinity": 0.18,
    "price_fit": 0.16,
    "popularity": 0.17,
    "recency": 0.05,
}


def resolve_profile_session(user_id: str, session_id: str | None, channel: str) -> str:
    """Bind a profile to existing omnichannel state without merging two users' carts."""
    customer_key = f"recommendation:{user_id}"
    candidate = session_id
    if candidate:
        candidate = session_store.get_or_create(candidate)
        owner = session_store.get_customer_id(candidate)
        if owner and owner != customer_key:
            candidate = None
    sid = session_store.link_customer(customer_key, candidate)
    session_store.record_channel(sid, channel)
    return sid


def _popularity_scores(store: InteractionStore) -> dict[str, float]:
    counts: Counter[str] = Counter()
    for demo_user in ("user_001", "user_011", "user_021", "user_031", "user_041"):
        for event in store.events(demo_user):
            if event["product_id"] and event["event_type"] in {"rec_click", "product_view"}:
                counts[event["product_id"]] += 1
    max_count = max(counts.values(), default=1)
    return {
        product.id: round(0.75 * (product.rating / 5.0) + 0.25 * (counts[product.id] / max_count), 6)
        for product in catalog.all
    }


def _price_fit(price: float, centroid: float, max_price: float) -> float:
    if centroid <= 0:
        return 0.5
    scale = max(100.0, centroid, max_price * 0.35)
    return max(0.0, 1.0 - abs(price - centroid) / scale)


def _reason_data(product: Any, components: dict[str, float], cold_start: bool) -> tuple[list[str], str]:
    reasons: list[str] = []
    facts: list[str] = []
    if cold_start:
        reasons.append("POPULAR_COLD_START")
        facts.append(f"its catalog rating is {product.rating:.1f}/5")
    if components["brand_affinity"] >= 0.25:
        reasons.append("PREFERRED_BRAND")
        facts.append(f"your positive interactions favor {product.brand}")
    if components["category_affinity"] >= 0.25:
        reasons.append("PREFERRED_CATEGORY")
        facts.append(f"your positive interactions favor {product.category.value} products")
    if components["price_fit"] >= 0.75 and not cold_start:
        reasons.append("PRICE_SIGNAL_MATCH")
        facts.append("its catalog price is close to your bounded interaction-price signal")
    if components["semantic"] >= 0.65:
        reasons.append("QUERY_MATCH")
        facts.append("it ranks highly for your normalized query")
    if components["recency"] > 0:
        reasons.append("RECENTLY_VIEWED")
        facts.append("you recently viewed this catalog item")
    if not reasons:
        reasons.append("CATALOG_POPULARITY")
        facts.append(f"its catalog rating is {product.rating:.1f}/5")
    elif not any(
        product.brand in fact
        or any(
            phrase in fact
            for phrase in ("catalog price", "normalized query", "recently viewed", "catalog rating")
        )
        for fact in facts
    ):
        facts.append(f"its catalog rating is {product.rating:.1f}/5")
    return reasons, "Recommended because " + "; ".join(facts) + "."


def bounded_preference_context(
    user_id: str | None,
    session_id: str | None,
    store: InteractionStore = interaction_store,
) -> dict[str, Any]:
    """Allow-listed soft context for ShopAssist; it contains no chat text or PII."""
    if not user_id:
        return {}
    profile = store.profile(user_id)
    cart_ids = session_store.get_cart_ids(session_id) if session_id else []
    wishlist_ids = session_store.get_wishlist_ids(session_id) if session_id else []
    top_brands = sorted(
        profile["brand_affinity"], key=profile["brand_affinity"].get, reverse=True
    )[:2]
    top_categories = sorted(
        profile["category_affinity"], key=profile["category_affinity"].get, reverse=True
    )[:2]
    return {
        "preferred_brands": top_brands,
        "preferred_categories": top_categories,
        "price_centroid": profile["price_signal"]["centroid"],
        "recent_product_ids": profile["recent_views"][:5],
        "exclude_product_ids": sorted(set(cart_ids) | set(wishlist_ids)),
    }


def get_personalized_recommendations(
    user_id: str,
    session_id: str | None = None,
    channel: str = "oneshop",
    query: str = "",
    limit: int = 6,
    store: InteractionStore = interaction_store,
) -> dict[str, Any]:
    sid = resolve_profile_session(user_id, session_id, channel)
    profile = store.profile(user_id)
    cart_ids = set(session_store.get_cart_ids(sid))
    wishlist_ids = set(session_store.get_wishlist_ids(sid))
    excluded = cart_ids | wishlist_ids
    profile.update(
        {
            "cart_exclusions": sorted(cart_ids),
            "wishlist_exclusions": sorted(wishlist_ids),
            "channels": sorted(set(profile["channels"]) | set(session_store.get_channel_info(sid)["channels_used"])),
        }
    )

    normalized_query = " ".join(query.strip().lower().split())[:120]
    retrieval_query = normalized_query
    if not retrieval_query and not profile["cold_start"]:
        top_brand = max(profile["brand_affinity"], key=profile["brand_affinity"].get, default="")
        top_category = max(profile["category_affinity"], key=profile["category_affinity"].get, default="")
        retrieval_query = " ".join(part for part in (top_brand, top_category) if part)

    retrieval_method = "popularity"
    retrieved_ids: list[str] = []
    if retrieval_query:
        try:
            retrieved_ids, retrieval_meta = semantic_retrieve_with_meta(
                retrieval_query, top_k=len(catalog.all), exclude_ids=excluded
            )
            retrieval_method = str(retrieval_meta.get("method") or "keyword")
        except Exception:
            retrieved_ids = []
            retrieval_method = "catalog_fallback"
    candidate_ids = list(retrieved_ids)
    candidate_ids.extend(
        product.id
        for product in catalog.all
        if product.in_stock and product.id not in excluded and product.id not in candidate_ids
    )
    retrieval_rank = {product_id: index for index, product_id in enumerate(retrieved_ids)}
    popularity = _popularity_scores(store)
    max_price = max((p.price for p in catalog.all), default=1.0)
    recent = set(profile["recent_views"])
    scored: list[dict[str, Any]] = []

    for product_id in candidate_ids:
        product = catalog.get_by_id(product_id)
        if not product or not product.in_stock or product.id in excluded:
            continue
        rank = retrieval_rank.get(product.id)
        semantic = max(0.0, 1.0 - rank / max(1, len(retrieved_ids))) if rank is not None else 0.0
        components = {
            "semantic": round(semantic, 6),
            "brand_affinity": round(profile["brand_affinity"].get(product.brand, 0.0), 6),
            "category_affinity": round(
                profile["category_affinity"].get(product.category.value, 0.0), 6
            ),
            "price_fit": round(
                _price_fit(product.price, profile["price_signal"]["centroid"], max_price), 6
            ),
            "popularity": popularity.get(product.id, round(product.rating / 5.0, 6)),
            "recency": 1.0 if product.id in recent else 0.0,
        }
        total = sum(components[key] * weight for key, weight in SCORE_WEIGHTS.items())
        reason_codes, explanation = _reason_data(product, components, profile["cold_start"])
        scored.append(
            {
                "product": product.model_dump(mode="json"),
                "score": round(total, 6),
                "score_breakdown": components,
                "reason_codes": reason_codes,
                "explanation": explanation,
            }
        )

    scored.sort(key=lambda item: (-item["score"], item["product"]["id"]))
    diversified: list[dict[str, Any]] = []
    brand_counts: Counter[str] = Counter()
    for item in scored:
        brand = item["product"]["brand"]
        if brand_counts[brand] >= 2:
            continue
        diversified.append(item)
        brand_counts[brand] += 1
        if len(diversified) >= limit:
            break
    if len(diversified) < limit:
        selected = {item["product"]["id"] for item in diversified}
        diversified.extend(item for item in scored if item["product"]["id"] not in selected)
        diversified = diversified[:limit]

    return {
        "user_id": user_id,
        "session_id": sid,
        "channel": channel,
        "version": store.version(user_id),
        "retrieval_method": retrieval_method,
        "profile": profile,
        "recommendations": diversified,
    }
