"""Tests for Smart Cart output guardrails."""

from app.models.schemas import BundleSuggestion, CrossSellItem, Product, ProductCategory
from app.services.smart_cart_guardrails import validate_smart_cart_output
from app.services.product_catalog import catalog


def _product(product_id: str) -> Product:
    product = catalog.get_by_id(product_id)
    assert product is not None
    return product


def test_validator_removes_cross_sell_already_in_cart():
    phone = _product("samsung-a54")
    case = _product("phone-case-universal")
    smart = {
        "cart": [phone],
        "cross_sell_suggestions": [
            CrossSellItem(product=case, rate=82, reason="82% of buyers also added this"),
            CrossSellItem(product=phone, rate=99, reason="should be removed"),
        ],
        "bundles": [],
        "nudge": "Save $50 today!",
        "checkout_tip": "",
        "ai_powered": False,
        "subtotal": phone.price,
        "discount": 0,
        "total": phone.price,
        "estimated_savings": 0,
    }
    result = validate_smart_cart_output(smart)
    assert len(result["cross_sell_suggestions"]) == 1
    assert result["cross_sell_suggestions"][0].product.id == case.id
    assert result["nudge"] != "Save $50 today!"


def test_validator_caps_bundle_count_and_recalculates_totals():
    phone = _product("samsung-a54")
    case = _product("phone-case-universal")
    bundle = BundleSuggestion(
        name="Phone Essentials Bundle",
        products=[case],
        product_ids=[case.id],
        total_price=26.1,
        original_price=29.0,
        discount_percent=10,
        savings=2.9,
        reason="Protect your new phone — save 10%",
    )
    smart = {
        "cart": [phone],
        "cross_sell_suggestions": [],
        "bundles": [bundle, bundle],
        "nudge": "Checkout now",
        "checkout_tip": "",
        "ai_powered": False,
        "subtotal": phone.price,
        "discount": 5.8,
        "total": phone.price - 5.8,
        "estimated_savings": 5.8,
    }
    result = validate_smart_cart_output(smart)
    assert len(result["bundles"]) == 1
    assert result["discount"] == 2.9
    assert result["total"] == round(phone.price - 2.9, 2)


def test_validator_drops_bundle_when_all_products_already_in_cart():
    phone = _product("samsung-a54")
    smart = {
        "cart": [phone],
        "cross_sell_suggestions": [],
        "bundles": [
            BundleSuggestion(
                name="Bad AI Bundle",
                products=[phone],
                product_ids=[phone.id],
                total_price=phone.price,
                savings=15,
                reason="invalid",
            )
        ],
        "nudge": "",
        "checkout_tip": "",
        "ai_powered": False,
        "subtotal": phone.price,
        "discount": 15,
        "total": phone.price - 15,
        "estimated_savings": 15,
    }
    result = validate_smart_cart_output(smart)
    assert result["bundles"] == []
    assert result["discount"] == 0
    assert result["total"] == phone.price
