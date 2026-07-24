"""Validate Smart Cart rule output before returning to clients."""

from __future__ import annotations

from typing import Any

from app.models.schemas import BundleSuggestion, CrossSellItem, Product, ProductCategory
from app.services.product_catalog import catalog

MAX_CROSS_SELL = 2
MAX_BUNDLES = 1

_DEFAULT_NUDGE = "Review your cart and compatible add-ons before checkout."
_EMPTY_NUDGE = "Add items to your cart to see compatible add-ons."


def _recalculate_bundle(bundle: BundleSuggestion, products: list[Product]) -> BundleSuggestion:
    original_total = round(sum(product.price for product in products), 2)
    return bundle.model_copy(update={
        "products": products,
        "product_ids": [product.id for product in products],
        "original_price": original_total,
        "total_price": original_total,
        "discount_percent": 0.0,
        "savings": 0.0,
        "reason": "Compatible add-ons selected from the current catalog.",
    })


def _catalog_product(product_id: str, cart_ids: set[str]) -> Product | None:
    product = catalog.get_by_id(product_id)
    if not product or not product.in_stock or product.id in cart_ids:
        return None
    return product


def validate_smart_cart_output(smart: dict[str, Any]) -> dict[str, Any]:
    cart: list[Product] = list(smart.get("cart") or [])
    cart_ids = {product.id for product in cart}

    cross_sell: list[CrossSellItem] = []
    seen_cross_sell: set[str] = set()
    for item in smart.get("cross_sell_suggestions", []):
        product = _catalog_product(item.product.id, cart_ids)
        if not product or product.id in seen_cross_sell:
            continue
        seen_cross_sell.add(product.id)
        cross_sell.append(CrossSellItem(
            product=product,
            rate=0,
            reason="Compatible catalog add-on",
        ))
        if len(cross_sell) >= MAX_CROSS_SELL:
            break

    bundles: list[BundleSuggestion] = []
    for bundle in smart.get("bundles", [])[:MAX_BUNDLES]:
        missing_products = [
            product
            for product_id in bundle.product_ids
            if (product := _catalog_product(product_id, cart_ids))
        ]
        if not missing_products:
            continue
        bundles.append(_recalculate_bundle(bundle, missing_products))

    subtotal = round(sum(product.price for product in cart), 2)
    one_time_total = round(
        sum(product.price for product in cart if product.category != ProductCategory.PLAN),
        2,
    )
    monthly_total = round(
        sum(product.price for product in cart if product.category == ProductCategory.PLAN),
        2,
    )

    return {
        **smart,
        "cart": cart,
        "cross_sell_suggestions": cross_sell,
        "bundles": bundles,
        "nudge": _DEFAULT_NUDGE if cart else _EMPTY_NUDGE,
        "checkout_tip": "",
        "subtotal": subtotal,
        "discount": 0.0,
        "total": subtotal,
        "estimated_savings": 0.0,
        "one_time_total": one_time_total,
        "monthly_total": monthly_total,
    }
