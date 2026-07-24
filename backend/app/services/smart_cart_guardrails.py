"""Validate Smart Cart rule output before returning to clients."""

from __future__ import annotations

import re
from typing import Any

from app.models.schemas import BundleSuggestion, CrossSellItem, Product

MAX_CROSS_SELL = 2
MAX_BUNDLES = 1

_DEFAULT_NUDGE = "Your cart is waiting — complete checkout for free shipping today!"


def _recalculate_bundle(bundle: BundleSuggestion, products: list[Product]) -> BundleSuggestion:
    original_total = sum(product.price for product in products)
    discount_percent = bundle.discount_percent or 0.0
    if discount_percent > 0:
        savings = round(original_total * discount_percent / 100, 2)
    else:
        savings = round(min(bundle.savings, original_total), 2)
    return bundle.model_copy(update={
        "products": products,
        "product_ids": [product.id for product in products],
        "original_price": round(original_total, 2),
        "total_price": round(max(original_total - savings, 0), 2),
        "savings": savings,
    })


def _sanitize_nudge(nudge: str, checkout_tip: str, discount: float) -> tuple[str, str]:
    """Prevent LLM nudge from claiming savings that rules did not compute."""
    cleaned_nudge = (nudge or "").strip()
    cleaned_tip = (checkout_tip or "").strip()
    if discount <= 0 and re.search(r"\bsave(?:s|d)?\s+\$", cleaned_nudge, re.I):
        cleaned_nudge = _DEFAULT_NUDGE
    if discount <= 0 and re.search(r"\b\d+\s*%\s*off", cleaned_nudge, re.I):
        cleaned_nudge = _DEFAULT_NUDGE
    return cleaned_nudge, cleaned_tip


def validate_smart_cart_output(smart: dict[str, Any]) -> dict[str, Any]:
    cart: list[Product] = list(smart.get("cart") or [])
    cart_ids = {product.id for product in cart}

    cross_sell: list[CrossSellItem] = [
        item for item in smart.get("cross_sell_suggestions", [])
        if item.product.id not in cart_ids
    ][:MAX_CROSS_SELL]

    bundles: list[BundleSuggestion] = []
    for bundle in smart.get("bundles", [])[:MAX_BUNDLES]:
        missing_products = [product for product in bundle.products if product.id not in cart_ids]
        if not missing_products:
            continue
        if len(missing_products) != len(bundle.products):
            bundles.append(_recalculate_bundle(bundle, missing_products))
        else:
            bundles.append(bundle)

    subtotal = round(sum(product.price for product in cart), 2)
    discount = round(sum(bundle.savings for bundle in bundles), 2)
    total = round(max(subtotal - discount, 0), 2)
    nudge, checkout_tip = _sanitize_nudge(
        smart.get("nudge", ""),
        smart.get("checkout_tip", ""),
        discount,
    )

    return {
        **smart,
        "cart": cart,
        "cross_sell_suggestions": cross_sell,
        "bundles": bundles,
        "nudge": nudge,
        "checkout_tip": checkout_tip,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "estimated_savings": discount,
    }
