from typing import Any

from app.models.schemas import BundleSuggestion, CrossSellItem, Product, ProductCategory
from app.services.interaction_store import interaction_store
from app.services.smart_cart_guardrails import validate_smart_cart_output
from app.services.product_catalog import catalog
from app.services.session_store import session_store

CO_PURCHASE_MAP: dict[str, list[dict[str, Any]]] = {
    "phone:Apple": [
        {"tag": "audio", "brand": "Apple"},
        {"tag": "case", "brand": None},
        {"tag": "charger", "brand": "Apple"},
    ],
    "phone:Samsung": [
        {"tag": "audio", "brand": "Samsung"},
        {"tag": "case", "brand": None},
    ],
    "phone:Google": [
        {"tag": "audio", "brand": None},
        {"tag": "case", "brand": None},
    ],
    "phone:*": [
        {"tag": "case", "brand": None},
        {"tag": "audio", "brand": None},
    ],
    "tablet:*": [
        {"tag": "case", "brand": None},
    ],
}

BUNDLE_RULES: list[dict[str, Any]] = [
    {
        "name": "Phone Essentials Bundle",
        "trigger_categories": [ProductCategory.PHONE],
        "suggest_tags": ["case"],
        "discount_percent": 0,
        "description": "A protective add-on selected from the current catalog.",
    },
    {
        "name": "Device + Plan Bundle",
        "trigger_categories": [ProductCategory.PHONE, ProductCategory.TABLET],
        "suggest_categories": [ProductCategory.PLAN],
        "discount_percent": 0,
        "description": "A plan option selected from the current catalog.",
    },
]


def _cart_tags(cart: list[Product]) -> set[str]:
    tags: set[str] = set()
    for product in cart:
        tags.update(product.tags)
    return tags


def _resolve_user_id(session_id: str, user_id: str | None = None) -> str | None:
    if user_id:
        return user_id
    customer_id = session_store.get_customer_id(session_id)
    if customer_id and customer_id.startswith("recommendation:"):
        return customer_id.split(":", 1)[1]
    return None


def _load_profile(session_id: str, user_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_user_id(session_id, user_id)
    if not resolved:
        return {}
    customer_id = session_store.get_customer_id(session_id)
    expected = f"recommendation:{resolved}"
    if customer_id and customer_id != expected:
        return {}
    return interaction_store.profile(resolved)


def _preferred_brands(profile: dict[str, Any], limit: int = 2) -> list[str]:
    affinity = profile.get("brand_affinity") or {}
    return sorted(affinity, key=affinity.get, reverse=True)[:limit]


def _product_preference_score(product: Product, profile: dict[str, Any]) -> float:
    score = product.rating
    brand_affinity = profile.get("brand_affinity") or {}
    category_affinity = profile.get("category_affinity") or {}
    score += brand_affinity.get(product.brand, 0) * 2.5
    score += category_affinity.get(product.category.value, 0) * 1.5
    centroid = (profile.get("price_signal") or {}).get("centroid") or 0
    if centroid > 0:
        score += max(0.0, 1.0 - abs(product.price - centroid) / max(centroid, 100.0))
    return score


def _find_product_by_tag(
    tag: str,
    brand: str | None,
    exclude_ids: set[str],
    profile: dict[str, Any] | None = None,
) -> Product | None:
    candidates = [
        p for p in catalog.all
        if tag in p.tags
        and p.id not in exclude_ids
        and p.in_stock
        and (brand is None or p.brand.lower() == brand.lower())
    ]
    if not candidates and brand:
        candidates = [
            p for p in catalog.all
            if tag in p.tags and p.id not in exclude_ids and p.in_stock
        ]
    if profile:
        candidates.sort(
            key=lambda product: _product_preference_score(product, profile),
            reverse=True,
        )
    else:
        candidates.sort(key=lambda product: product.rating, reverse=True)
    return candidates[0] if candidates else None


def _find_product_by_category(
    category: ProductCategory,
    exclude_ids: set[str],
    profile: dict[str, Any] | None = None,
) -> Product | None:
    candidates = [
        p for p in catalog.all
        if p.category == category and p.id not in exclude_ids and p.in_stock
    ]
    if profile:
        candidates.sort(
            key=lambda product: _product_preference_score(product, profile),
            reverse=True,
        )
    else:
        candidates.sort(key=lambda product: product.rating, reverse=True)
    return candidates[0] if candidates else None

def get_cross_sell_suggestions(
    cart: list[Product],
    trigger_product: Product | None,
    profile: dict[str, Any] | None = None,
) -> list[CrossSellItem]:
    if not trigger_product:
        return []

    profile = profile or {}
    preferred = set(_preferred_brands(profile))
    category = trigger_product.category.value
    brand = trigger_product.brand
    key_specific = f"{category}:{brand}"
    key_generic = f"{category}:*"
    rules = CO_PURCHASE_MAP.get(key_specific, CO_PURCHASE_MAP.get(key_generic, []))
    if not rules:
        return []

    cart_ids = {p.id for p in cart}
    suggestions: list[CrossSellItem] = []

    for rule in rules:
        product = _find_product_by_tag(rule["tag"], rule.get("brand"), cart_ids, profile)
        if not product:
            continue
        reason = "Compatible catalog add-on"
        if product.brand in preferred:
            reason += " · matches your recorded brand preference"
        suggestions.append(CrossSellItem(
            product=product,
            rate=0,
            reason=reason,
        ))

    return suggestions[:2]


def detect_bundles(
    cart: list[Product],
    profile: dict[str, Any] | None = None,
) -> list[BundleSuggestion]:
    if not cart:
        return []

    profile = profile or {}
    cart_ids = {p.id for p in cart}
    cart_categories = {p.category for p in cart}
    cart_tags = _cart_tags(cart)
    bundles: list[BundleSuggestion] = []
    for rule in BUNDLE_RULES:
        triggers = rule["trigger_categories"]
        if not any(category in cart_categories for category in triggers):
            continue

        suggested_products: list[Product] = []

        for tag in rule.get("suggest_tags", []):
            if tag in cart_tags:
                continue
            product = _find_product_by_tag(tag, None, cart_ids, profile)
            if product:
                suggested_products.append(product)

        for category in rule.get("suggest_categories", []):
            if category in cart_categories:
                continue
            product = _find_product_by_category(category, cart_ids, profile)
            if product:
                suggested_products.append(product)
        if not suggested_products:
            continue

        original_total = sum(p.price for p in suggested_products)
        discount_percent = 0.0
        savings = 0.0
        bundle_price = round(original_total, 2)

        bundles.append(BundleSuggestion(
            name=rule["name"],
            products=suggested_products,
            product_ids=[p.id for p in suggested_products],
            total_price=bundle_price,
            original_price=round(original_total, 2),
            discount_percent=discount_percent,
            savings=savings,
            reason=rule["description"],
        ))

    return bundles[:1]


def _resolve_trigger_product(cart: list[Product], session_id: str) -> Product | None:
    last_id = session_store.get_last_cart_add(session_id)
    if last_id:
        product = catalog.get_by_id(last_id)
        if product and any(p.id == last_id for p in cart):
            return product

    for product in cart:
        if product.category == ProductCategory.PHONE:
            return product
    return cart[0] if cart else None


def _calculate_cart_totals(cart: list[Product]) -> tuple[float, float, float]:
    subtotal = round(sum(p.price for p in cart), 2)
    return subtotal, 0.0, subtotal


def format_smart_cart_chat_hints(smart: dict[str, Any]) -> dict[str, Any]:
    """Read-only Smart Cart facts for ShopAssist — no cart mutation."""
    cross_sell = [
        {
            "product_id": item.product.id,
            "name": item.product.name,
            "price": item.product.price,
            "reason": item.reason,
        }
        for item in smart.get("cross_sell_suggestions", [])
    ]
    bundles = [
        {
            "name": bundle.name,
            "reason": bundle.reason,
            "products": [product.name for product in bundle.products],
        }
        for bundle in smart.get("bundles", [])
    ]
    parts: list[str] = []
    if cross_sell:
        parts.append(
            "Frequently bought together: "
            + "; ".join(f"{item['name']} ({item['reason']})" for item in cross_sell)
        )
    if bundles:
        bundle = bundles[0]
        parts.append(
            f"Compatible add-on group: {bundle['name']} — {bundle['reason']} "
            f"({', '.join(bundle['products'])})"
        )
    return {
        "cross_sell": cross_sell,
        "bundles": bundles,
        "summary": " ".join(parts),
        "note": (
            "These are catalog-grounded Smart Cart suggestions from the current cart and profile. "
            "You may mention them, but never add items to the cart."
        ),
    }


def smart_cart_chat_suffix(smart: dict[str, Any]) -> str:
    hints = format_smart_cart_chat_hints(smart)
    summary = hints.get("summary", "")
    if not summary:
        return ""
    return f" Smart Cart suggests: {summary} Add from the cart panel or ask me to propose a bundle."


def get_smart_cart(session_id: str, user_id: str | None = None) -> dict[str, Any]:
    profile = _load_profile(session_id, user_id)
    cart = session_store.get_cart(session_id)
    bundles = detect_bundles(cart, profile)
    trigger = _resolve_trigger_product(cart, session_id)
    cross_sell = get_cross_sell_suggestions(cart, trigger, profile)
    subtotal, discount, total = _calculate_cart_totals(cart)
    one_time_total = round(
        sum(product.price for product in cart if product.category != ProductCategory.PLAN),
        2,
    )
    monthly_total = round(
        sum(product.price for product in cart if product.category == ProductCategory.PLAN),
        2,
    )
    nudge = "Review your cart and compatible add-ons before checkout."
    checkout_tip = ""
    ai_powered = False

    if not cart:
        nudge = "Add items to your cart to see compatible add-ons."

    result = {
        "cart": cart,
        "bundles": bundles,
        "cross_sell_suggestions": cross_sell,
        "nudge": nudge,
        "checkout_tip": checkout_tip,
        "ai_powered": ai_powered,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "estimated_savings": discount,
        "one_time_total": one_time_total,
        "monthly_total": monthly_total,
    }
    return validate_smart_cart_output(result)


# Kept for orchestrator import compatibility
def _rule_bundles(cart: list[Product]) -> list[BundleSuggestion]:
    return detect_bundles(cart)
