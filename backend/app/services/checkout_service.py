from app.models.schemas import CheckoutResponse, Product, ProductCategory
from app.services.session_store import session_store


def calculate_cadence_totals(cart: list[Product]) -> tuple[float, float]:
    one_time_total = round(
        sum(product.price for product in cart if product.category != ProductCategory.PLAN),
        2,
    )
    monthly_total = round(
        sum(product.price for product in cart if product.category == ProductCategory.PLAN),
        2,
    )
    return one_time_total, monthly_total


def calculate_totals(cart: list[Product]) -> tuple[float, float, float, float]:
    """Return catalog-owned totals without manufacturing an offer.

    `subtotal` and `total` are retained for API compatibility. Mixed billing
    cadences are exposed separately by `calculate_cadence_totals`.
    """
    subtotal = round(sum(product.price for product in cart), 2)
    return subtotal, 0.0, 0.0, subtotal


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

    subtotal, bundle_savings, discount_amount, total = calculate_totals(cart)
    one_time_total, monthly_total = calculate_cadence_totals(cart)

    order_id = session_store.record_order(sid, {
        "customer_name": customer_name,
        "email": email,
        "payment_last4": payment_last4,
        "items": [p.id for p in cart],
        "subtotal": subtotal,
        "savings": bundle_savings,
        "discount": discount_amount,
        "total": total,
        "one_time_total": one_time_total,
        "monthly_total": monthly_total,
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
        one_time_total=one_time_total,
        monthly_total=monthly_total,
        message=f"Thank you {customer_name}! Order {order_id} confirmed. A receipt was sent to {email}.",
    )
