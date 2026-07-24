from app.models.schemas import CheckoutResponse, Product, ProductCategory
from app.services.product_catalog import catalog
from app.services.session_store import session_store


def _estimate_bundle_savings(cart: list[Product]) -> float:
    savings = 0.0
    categories = {p.category for p in cart}
    if ProductCategory.PHONE in categories:
        savings += 15.0
        if ProductCategory.ACCESSORY in categories:
            savings += 20.0
    elif ProductCategory.TABLET in categories:
        savings += 10.0
    return savings


def calculate_totals(cart: list[Product], discount_pct: float = 0) -> tuple[float, float, float, float]:
    subtotal = sum(p.price for p in cart)
    bundle_savings = _estimate_bundle_savings(cart)
    discount_amount = subtotal * (discount_pct / 100) if discount_pct else 0
    total = max(subtotal - bundle_savings - discount_amount, 0)
    return subtotal, bundle_savings, discount_amount, total


def complete_checkout(
    session_id: str,
    customer_name: str,
    email: str,
    payment_last4: str,
) -> CheckoutResponse:
    sid = session_store.get_or_create(session_id)
    cart = session_store.get_cart(sid)

    if not cart:
        raise ValueError("Cart is empty")

    discount_pct = session_store.get_recovery_discount(sid)
    subtotal, bundle_savings, discount_amount, total = calculate_totals(cart, discount_pct)

    order_id = session_store.record_order(sid, {
        "customer_name": customer_name,
        "email": email,
        "payment_last4": payment_last4,
        "items": [p.id for p in cart],
        "subtotal": subtotal,
        "savings": bundle_savings,
        "discount": discount_amount,
        "total": total,
    })

    items = list(cart)
    session_store.clear_cart(sid)
    session_store.clear_abandonment(sid)

    return CheckoutResponse(
        session_id=sid,
        order_id=order_id,
        items=items,
        subtotal=subtotal,
        savings=bundle_savings,
        discount=discount_amount,
        total=total,
        message=f"Thank you {customer_name}! Order {order_id} confirmed. A receipt was sent to {email}.",
    )
