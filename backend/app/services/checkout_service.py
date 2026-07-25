from app.models.schemas import CheckoutResponse, Product, ProductCategory
from app.services.receipt_email_service import (
    EVA_EMAIL,
    EVA_NAME,
    deliver_receipt_via_eva,
    mask_email,
    receipt_view_path,
)
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
    delivery = deliver_receipt_via_eva(
        session_id=sid,
        order_id=order_id,
        customer_name=customer_name,
        email=email,
        payment_last4=payment_last4,
        items=items,
        one_time_total=one_time_total,
        monthly_total=monthly_total,
        subtotal=subtotal,
    )
    session_store.clear_cart(sid)
    session_store.clear_abandonment(sid)

    masked_email = mask_email(email)
    if delivery.get("inbox_delivered"):
        receipt_note = (
            f"{EVA_NAME} ({EVA_EMAIL}) sent your HTML receipt to {masked_email}'s inbox."
        )
        inbox_sent = True
    else:
        if delivery.get("delivery_error") == "resend_sandbox_recipient":
            receipt_note = (
                f"Receipt saved for {masked_email}. Resend test mode only delivers to the "
                f"email on your Resend account — use that address at checkout, verify a domain "
                f"at resend.com/domains, or set EVA_GMAIL_APP_PASSWORD for Gmail delivery."
            )
        else:
            receipt_note = (
                f"Receipt saved securely for {masked_email}. "
                f"Inbox delivery failed — open the receipt link below, or check backend logs."
            )
        inbox_sent = False

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
        message=f"Thank you {customer_name}! Order {order_id} confirmed. {receipt_note}",
        receipt_from=f"{EVA_NAME} <{EVA_EMAIL}>",
        receipt_sent=inbox_sent,
        receipt_url=receipt_view_path(order_id, sid),
    )
