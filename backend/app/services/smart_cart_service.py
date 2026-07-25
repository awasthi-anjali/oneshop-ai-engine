from typing import Any

from app.models.schemas import BundleSuggestion, CrossSellItem, Product, ProductCategory
from app.services.interaction_store import interaction_store
from app.services.smart_cart_guardrails import validate_smart_cart_output
from app.services.product_catalog import catalog
from app.services.session_store import session_store

PHONE_ACCESSORY_IDS: dict[str, list[str]] = {
    "Apple": ["airpods-pro"],
    "Samsung": ["galaxy-buds2-pro"],
    "Google": ["phone-case-universal"],
    "OnePlus": ["phone-case-universal"],
}
DEFAULT_PHONE_ACCESSORY_IDS = ["phone-case-universal"]
DEFAULT_PHONE_PLAN_ID = "unlimited-essential"
TABLET_PLAN_ID = "data-only-plan"


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

    cart_ids = {p.id for p in cart}
    cart_categories = {p.category for p in cart}
    candidate_ids: list[str] = []
    if trigger_product.category == ProductCategory.PHONE:
        candidate_ids.extend(
            PHONE_ACCESSORY_IDS.get(
                trigger_product.brand,
                DEFAULT_PHONE_ACCESSORY_IDS,
            )
        )
        if ProductCategory.PLAN not in cart_categories:
            candidate_ids.append(DEFAULT_PHONE_PLAN_ID)
    elif trigger_product.category == ProductCategory.TABLET:
        if ProductCategory.PLAN not in cart_categories:
            candidate_ids.append(TABLET_PLAN_ID)
    else:
        return []

    suggestions: list[CrossSellItem] = []

    for product_id in candidate_ids:
        product = catalog.get_by_id(product_id)
        if not product or not product.in_stock or product.id in cart_ids:
            continue
        if product.category == ProductCategory.PLAN:
            reason = "General phone service option; eligibility is not assumed"
        elif "audio" in product.tags:
            reason = f"Same-brand wireless audio option for {trigger_product.brand}"
        else:
            reason = "Protective case option; verify model fit before purchase"
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

    cart_ids = {p.id for p in cart}
    cart_categories = {p.category for p in cart}
    phone = next(
        (product for product in cart if product.category == ProductCategory.PHONE),
        None,
    )
    if not phone:
        return []

    suggested_products: list[Product] = []
    case = catalog.get_by_id("phone-case-universal")
    if case and case.in_stock and case.id not in cart_ids:
        suggested_products.append(case)
    if ProductCategory.PLAN not in cart_categories:
        plan = catalog.get_by_id(DEFAULT_PHONE_PLAN_ID)
        if plan and plan.in_stock and plan.id not in cart_ids:
            suggested_products.append(plan)

    if len(suggested_products) < 2:
        return []

    original_total = round(sum(product.price for product in suggested_products), 2)
    return [
        BundleSuggestion(
            name="Complete your phone setup",
            products=suggested_products,
            product_ids=[product.id for product in suggested_products],
            total_price=original_total,
            original_price=original_total,
            discount_percent=0,
            savings=0,
            reason=(
                "A protective case option and a general phone plan from the "
                "current catalog. Verify case fit and plan eligibility."
            ),
        )
    ]


def _resolve_trigger_product(cart: list[Product], session_id: str) -> Product | None:
    last_id = session_store.get_last_cart_add(session_id)
    if last_id:
        product = catalog.get_by_id(last_id)
        if (
            product
            and product.category == ProductCategory.PHONE
            and any(p.id == last_id for p in cart)
        ):
            return product

    for product in cart:
        if product.category == ProductCategory.PHONE:
            return product
    if last_id:
        product = catalog.get_by_id(last_id)
        if product and any(p.id == last_id for p in cart):
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
            "Optional catalog suggestions: "
            + "; ".join(f"{item['name']} ({item['reason']})" for item in cross_sell)
        )
    if bundles:
        bundle = bundles[0]
        parts.append(
            f"Suggested item set: {bundle['name']} — {bundle['reason']} "
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
    grouped_ids = {
        product_id
        for bundle in bundles
        for product_id in bundle.product_ids
    }
    cross_sell = [
        item for item in cross_sell if item.product.id not in grouped_ids
    ]
    subtotal, discount, total = _calculate_cart_totals(cart)
    one_time_total = round(
        sum(product.price for product in cart if product.category != ProductCategory.PLAN),
        2,
    )
    monthly_total = round(
        sum(product.price for product in cart if product.category == ProductCategory.PLAN),
        2,
    )
    nudge = "Review trusted totals and optional catalog suggestions before demo checkout."
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
