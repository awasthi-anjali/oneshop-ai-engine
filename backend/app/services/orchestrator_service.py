"""
Central AI orchestrator — one LLM call drives intent, recommendations,
next actions, and smart cart. Rules validate AI output; fallback when no key.
"""

import json

from app.config import settings
from app.models.schemas import (
    BundleSuggestion,
    CustomerIntent,
    NextBestAction,
    Product,
    RecommendationItem,
)
from app.services.ai_client import get_openai_client, is_ai_enabled
from app.services.catalog_retrieval import catalog_compact, semantic_retrieve
from app.services.checkout_service import calculate_totals
from app.services.customer_context import build_customer_context, get_funnel_stage
from app.services.intent_engine import extract_intent_from_signals
from app.services.next_best_action_service import get_next_best_actions
from app.services.product_catalog import catalog
from app.services.recommendation_validator import validate_recommendations
from app.services.session_store import session_store
from app.services.smart_cart_service import _rule_bundles, get_smart_cart

ORCHESTRATOR_PROMPT = """You are the Commerce Intelligence Orchestrator for OneShop.
Given customer context and the product catalog, return ONE JSON object with all decisions.

{
  "intent": {
    "summary": "2-3 sentence natural language summary",
    "categories": ["phone", "plan"],
    "brands": ["Apple"],
    "tags": ["premium", "camera"],
    "price_min": null,
    "price_max": null,
    "price_avg": null,
    "funnel_stage": "new|browsing|wishlisted|cart",
    "ecosystem": "e.g. Apple ecosystem",
    "purchase_readiness": "low|medium|high"
  },
  "recommendations": [
    {"product_id": "must-be-from-catalog", "reason": "1 sentence why this fits"}
  ],
  "next_actions": [
    {"action": "snake_case_id", "label": "Short user-facing label", "priority": 1}
  ],
  "smart_cart": {
    "nudge": "1 sentence to encourage checkout or add items",
    "checkout_tip": "compatibility tip or empty string",
    "bundles": [
      {
        "name": "Bundle name",
        "product_ids": ["id1", "id2"],
        "reason": "Why this bundle",
        "savings": 15
      }
    ]
  }
}

Rules:
- Only use product_ids from the catalog. Pick up to 6 recommendations.
- Exclude items already in cart or wishlist from recommendations.
- Prioritize cross-sell: phone→plan→accessory.
- Weight signals: cart > wishlist > viewed > chat.
- Bundles: suggest phone+plan or phone+accessory when relevant; savings 10-20.
- next_actions: 2-3 contextual conversion steps for the funnel stage."""


def _merge_signals(wishlist: list[Product], cart: list[Product], viewed: list[Product]) -> list[Product]:
    seen: set[str] = set()
    merged: list[Product] = []
    for p in cart + wishlist + viewed:
        if p.id not in seen:
            seen.add(p.id)
            merged.append(p)
    return merged


def _build_retrieval_query(context: dict, chat_snippets: list[str]) -> str:
    parts: list[str] = []
    for key in ("cart", "wishlist", "viewed_products"):
        for p in context.get(key, []):
            parts.append(f"{p.get('name', '')} {p.get('brand', '')} {' '.join(p.get('tags', []))}")
    parts.extend(chat_snippets[-2:])
    return " ".join(parts).strip() or "popular phones plans accessories"


def _resolve_bundles(
    ai_bundles: list[dict],
    cart: list[Product],
    rule_bundles: list[BundleSuggestion],
) -> list[BundleSuggestion]:
    resolved: list[BundleSuggestion] = []
    cart_ids = {p.id for p in cart}

    for raw in ai_bundles[:3]:
        pids = [pid for pid in raw.get("product_ids", []) if catalog.get_by_id(pid)]
        products = catalog.get_by_ids(pids)
        if len(products) < 2:
            continue
        savings = float(raw.get("savings", 15))
        resolved.append(BundleSuggestion(
            name=raw.get("name", "Suggested Bundle"),
            products=products,
            product_ids=pids,
            total_price=sum(p.price for p in products),
            savings=savings,
            reason=raw.get("reason", "Bundle and save"),
        ))

    if resolved:
        return resolved

    return rule_bundles


def _fallback_profile(session_id: str, limit: int) -> dict:
    """Compose profile from existing services when AI unavailable."""
    from app.services.recommendation_engine import get_recommendations

    wishlist = session_store.get_wishlist(session_id)
    cart = session_store.get_cart(session_id)
    viewed = session_store.get_viewed(session_id)
    intent, recommendations, rec_ai = get_recommendations(session_id, limit=limit)
    stage, actions, nba_ai = get_next_best_actions(session_id)
    cart_items, bundles, nudge, tip, cart_ai, subtotal, savings = get_smart_cart(session_id)
    abandon = session_store.get_abandonment_status(session_id)

    return {
        "session_id": session_id,
        "intent": intent,
        "recommendations": recommendations,
        "next_actions": actions,
        "funnel_stage": stage,
        "cart": cart_items,
        "bundles": bundles,
        "nudge": nudge,
        "checkout_tip": tip,
        "subtotal": subtotal,
        "estimated_savings": savings,
        "ai_powered": rec_ai or nba_ai or cart_ai,
        "abandonment": abandon,
    }


def _ai_orchestrate(session_id: str, limit: int) -> dict | None:
    client = get_openai_client()
    if not client:
        return None

    wishlist = session_store.get_wishlist(session_id)
    cart = session_store.get_cart(session_id)
    viewed = session_store.get_viewed(session_id)
    exclude = {p.id for p in wishlist} | {p.id for p in cart}
    signals = _merge_signals(wishlist, cart, viewed)
    rule_intent = extract_intent_from_signals(wishlist, cart, viewed)

    context = build_customer_context(session_id)
    chat_snippets = context.get("recent_chat", [])
    retrieval_query = _build_retrieval_query(context, chat_snippets)

    # RAG-lite: semantic retrieve narrows catalog focus for the LLM
    retrieved_ids = semantic_retrieve(retrieval_query, top_k=12, exclude_ids=exclude)
    if retrieved_ids:
        catalog_slice = [
            item for item in catalog_compact(exclude_ids=exclude)
            if item["id"] in set(retrieved_ids)
        ]
        # Pad with full compact catalog if retrieval too narrow
        if len(catalog_slice) < 6:
            seen = {x["id"] for x in catalog_slice}
            for item in catalog_compact(exclude_ids=exclude):
                if item["id"] not in seen:
                    catalog_slice.append(item)
                if len(catalog_slice) >= 12:
                    break
    else:
        catalog_slice = catalog_compact(exclude_ids=exclude)

    user_payload = {
        "customer": context,
        "catalog": catalog_slice,
        "retrieval_focus": retrieved_ids,
        "exclude_product_ids": list(exclude),
    }

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": ORCHESTRATOR_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        return None

    # Parse intent (AI-first, rule fallback for missing fields)
    raw_intent = data.get("intent", {})
    intent = CustomerIntent(
        categories=raw_intent.get("categories", rule_intent.categories),
        brands=raw_intent.get("brands", rule_intent.brands),
        tags=raw_intent.get("tags", rule_intent.tags),
        price_min=raw_intent.get("price_min", rule_intent.price_min),
        price_max=raw_intent.get("price_max", rule_intent.price_max),
        price_avg=raw_intent.get("price_avg", rule_intent.price_avg),
        summary=raw_intent.get("summary", rule_intent.summary),
        funnel_stage=raw_intent.get("funnel_stage", rule_intent.funnel_stage),
        ecosystem=raw_intent.get("ecosystem", ""),
        purchase_readiness=raw_intent.get("purchase_readiness", ""),
    )

    # AI-first recommendations → rule validation
    raw_recs = data.get("recommendations", [])
    rec_ids = [r.get("product_id") for r in raw_recs if r.get("product_id")]
    rec_reasons = {r["product_id"]: r.get("reason", "") for r in raw_recs if r.get("product_id")}
    viewed_ids = set(session_store.get_viewed_ids(session_id))
    wishlist_ids = set(session_store.get_wishlist_ids(session_id))
    viewed_only = viewed_ids - {p.id for p in cart} - wishlist_ids

    if not signals:
        popular = sorted(catalog.all, key=lambda p: p.rating, reverse=True)
        recommendations = [
            RecommendationItem(product=p, score=p.rating, reason="Top rated in catalog")
            for p in popular[:limit]
        ]
    else:
        recommendations = validate_recommendations(
            rec_ids, rec_reasons, exclude, signals, intent, cart, viewed_only, limit
        )
        if not recommendations:
            # AI returned invalid IDs — semantic retrieve + validate as backup
            backup_ids = semantic_retrieve(retrieval_query, top_k=limit + 4, exclude_ids=exclude)
            recommendations = validate_recommendations(
                backup_ids, {}, exclude, signals, intent, cart, viewed_only, limit
            )

    # Next actions
    raw_actions = data.get("next_actions", [])
    next_actions = [
        NextBestAction(
            action=a.get("action", "explore"),
            label=a.get("label", "Explore products"),
            priority=a.get("priority", i + 1),
        )
        for i, a in enumerate(raw_actions[:3])
    ]
    if not next_actions:
        _, next_actions, _ = get_next_best_actions(session_id)

    # Smart cart
    raw_cart = data.get("smart_cart", {})
    rule_bundles = _rule_bundles(cart)
    bundles = _resolve_bundles(raw_cart.get("bundles", []), cart, rule_bundles)
    subtotal, estimated_savings, _, _ = calculate_totals(cart)
    nudge = raw_cart.get("nudge") or (
        "Add items to your cart to see bundle savings and checkout tips."
        if not cart else "Your cart is waiting — complete checkout for free shipping today!"
    )
    checkout_tip = raw_cart.get("checkout_tip", "")

    abandon = session_store.get_abandonment_status(session_id)

    return {
        "session_id": session_id,
        "intent": intent,
        "recommendations": recommendations,
        "next_actions": next_actions,
        "funnel_stage": intent.funnel_stage or get_funnel_stage(session_id),
        "cart": cart,
        "bundles": bundles,
        "nudge": nudge,
        "checkout_tip": checkout_tip,
        "subtotal": subtotal,
        "estimated_savings": estimated_savings,
        "ai_powered": True,
        "abandonment": abandon,
    }


def get_intelligence_profile(session_id: str | None, limit: int = 6) -> dict:
    """
    Single entry point for all Shop intelligence.
    AI orchestrates when key is set; otherwise falls back to rule services.
    """
    sid = session_store.get_or_create(session_id)

    if is_ai_enabled():
        profile = _ai_orchestrate(sid, limit)
        if profile:
            return profile

    return _fallback_profile(sid, limit)
