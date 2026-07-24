"""Tests for Smart Cart output guardrails."""

import uuid

from app.models.schemas import BundleSuggestion, CrossSellItem, Product, ProductCategory
from app.services.checkout_service import calculate_cadence_totals, calculate_totals
from app.services.smart_cart_guardrails import validate_smart_cart_output
from app.services.smart_cart_service import get_smart_cart
from app.services.product_catalog import catalog
from app.services.session_store import session_store


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
    assert result["cross_sell_suggestions"][0].rate == 0
    assert result["cross_sell_suggestions"][0].reason == "Compatible catalog add-on"
    assert result["nudge"] == "Review your cart and compatible add-ons before checkout."
    assert result["checkout_tip"] == ""


def test_validator_caps_bundle_count_without_discounting_unadded_products():
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
    assert result["bundles"][0].discount_percent == 0
    assert result["bundles"][0].savings == 0
    assert result["bundles"][0].total_price == case.price
    assert result["discount"] == 0
    assert result["total"] == phone.price
    assert result["one_time_total"] == phone.price
    assert result["monthly_total"] == 0


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


def test_validator_rejects_unknown_product_facts_and_llm_commerce_copy():
    phone = _product("samsung-a54")
    invented = _product("phone-case-universal").model_copy(update={
        "id": "invented-product",
        "name": "Free Premium Case",
        "price": 0.01,
    })
    result = validate_smart_cart_output({
        "cart": [phone],
        "cross_sell_suggestions": [
            CrossSellItem(product=invented, rate=99, reason="Guaranteed compatible"),
        ],
        "bundles": [
            BundleSuggestion(
                name="Free bundle",
                products=[invented],
                product_ids=[invented.id],
                total_price=0,
                discount_percent=100,
                savings=999,
                reason="Free today",
            ),
        ],
        "nudge": "Save $500 today with free shipping!",
        "checkout_tip": "Guaranteed compatible with a bonus.",
    })
    assert result["cross_sell_suggestions"] == []
    assert result["bundles"] == []
    assert result["nudge"] == "Review your cart and compatible add-ons before checkout."
    assert result["checkout_tip"] == ""
    assert result["discount"] == 0
    assert result["total"] == phone.price


def test_smart_cart_and_checkout_keep_billing_cadences_separate():
    sid = f"smart-cart-{uuid.uuid4().hex}"
    session_store.add_bundle_to_cart(sid, ["google-pixel-8", "unlimited-plus"])

    smart = get_smart_cart(sid)
    assert smart["one_time_total"] == 699
    assert smart["monthly_total"] == 85
    assert smart["discount"] == 0
    assert smart["estimated_savings"] == 0
    assert smart["total"] == smart["subtotal"] == 784
    assert all(item.rate == 0 for item in smart["cross_sell_suggestions"])
    assert all("buyers" not in item.reason.lower() for item in smart["cross_sell_suggestions"])
    assert all(bundle.savings == 0 for bundle in smart["bundles"])

    cart = session_store.get_cart(sid)
    assert calculate_totals(cart) == (784, 0.0, 0.0, 784)
    assert calculate_cadence_totals(cart) == (699, 85)


def test_abandonment_never_creates_an_untrusted_offer():
    sid = f"abandon-{uuid.uuid4().hex}"
    session_store.add_to_cart(sid, "google-pixel-8")
    assert session_store.mark_abandoned(sid)
    status = session_store.get_abandonment_status(sid)
    assert status["is_abandoned"] is True
    assert status["discount_offer"] == 0
    assert "%" not in status["recovery_message"]
    assert "off" not in status["recovery_message"].lower()
