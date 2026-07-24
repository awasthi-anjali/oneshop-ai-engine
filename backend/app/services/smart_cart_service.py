import json

from app.config import settings
from app.models.schemas import BundleSuggestion, Product, ProductCategory
from app.services.ai_client import get_openai_client
from app.services.checkout_service import calculate_totals
from app.services.product_catalog import catalog
from app.services.session_store import session_store

BUNDLE_RULES: list[tuple[set[ProductCategory], str, float]] = [
    ({ProductCategory.PHONE}, "Device + Plan Bundle", 15.0),
    ({ProductCategory.PHONE, ProductCategory.ACCESSORY}, "Complete Phone Kit", 20.0),
    ({ProductCategory.TABLET}, "Tablet + Data Plan", 10.0),
]

CART_PROMPT = """Analyze the customer's cart and suggest:
1. A short nudge message (1 sentence) to encourage checkout or add items
2. A checkout tip if something looks incompatible (e.g. tablet with low-data plan)

Return JSON: {"nudge": "...", "checkout_tip": "..."}"""


def _find_plan() -> Product | None:
    plans = [p for p in catalog.all if p.category == ProductCategory.PLAN]
    return plans[0] if plans else None


def _find_accessory_for_brand(brand: str) -> Product | None:
    accessories = [
        p for p in catalog.all
        if p.category == ProductCategory.ACCESSORY
        and (brand.lower() in p.brand.lower() or brand.lower() in " ".join(p.tags).lower())
    ]
    return accessories[0] if accessories else None


def _rule_bundles(cart: list[Product]) -> list[BundleSuggestion]:
    bundles: list[BundleSuggestion] = []
    cart_ids = {p.id for p in cart}
    categories = {p.category for p in cart}

    if ProductCategory.PHONE in categories:
        phone = next(p for p in cart if p.category == ProductCategory.PHONE)
        plan = _find_plan()
        if plan and plan.id not in cart_ids:
            total = phone.price + plan.price
            bundles.append(BundleSuggestion(
                name="Phone + Plan Bundle",
                products=[phone, plan],
                product_ids=[phone.id, plan.id],
                total_price=total,
                savings=15.0,
                reason=f"Pair your {phone.name} with a plan and save $15/mo",
            ))
        acc = _find_accessory_for_brand(phone.brand)
        if acc and acc.id not in cart_ids:
            total = phone.price + acc.price
            bundles.append(BundleSuggestion(
                name="Complete Phone Kit",
                products=[phone, acc],
                product_ids=[phone.id, acc.id],
                total_price=total,
                savings=20.0,
                reason=f"Protect and enhance your {phone.name}",
            ))

    if not bundles and cart:
        total = sum(p.price for p in cart)
        bundles.append(BundleSuggestion(
            name="Your Current Cart",
            products=cart,
            product_ids=[p.id for p in cart],
            total_price=total,
            savings=0,
            reason="Review your selections before checkout",
        ))

    return bundles[:3]


def get_smart_cart(session_id: str) -> tuple[list[Product], list[BundleSuggestion], str, str, bool, float, float]:
    cart = session_store.get_cart(session_id)
    bundles = _rule_bundles(cart)
    subtotal, estimated_savings, _, _ = calculate_totals(cart)
    nudge = "Your cart is waiting — complete checkout for free shipping today!"
    checkout_tip = ""
    ai_powered = False

    client = get_openai_client()
    if client and cart:
        try:
            cart_data = [{"name": p.name, "category": p.category.value, "price": p.price} for p in cart]
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": CART_PROMPT},
                    {"role": "user", "content": json.dumps({"cart": cart_data, "bundles": [b.name for b in bundles]})},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
            )
            data = json.loads(response.choices[0].message.content or "{}")
            nudge = data.get("nudge", nudge)
            checkout_tip = data.get("checkout_tip", "")
            ai_powered = True
        except Exception:
            pass
    elif not cart:
        nudge = "Add items to your cart to see bundle savings and checkout tips."

    return cart, bundles, nudge, checkout_tip, ai_powered, subtotal, estimated_savings
