from app.models.schemas import Product, ProductCategory
from app.services.receipt_email_service import (
    EVA_EMAIL,
    EVA_NAME,
    deliver_receipt_via_eva,
    get_receipt_html,
    mask_email,
    render_receipt_html,
)


def _sample_product() -> Product:
    return Product(
        id="google-pixel-8",
        name="Google Pixel 8",
        category=ProductCategory.PHONE,
        brand="Google",
        price=699,
        description="Camera phone",
        features=[],
        specs={},
        image_url="",
        rating=4.6,
        in_stock=True,
        tags=["android"],
    )


def test_receipt_html_shows_eva_sender():
    html = render_receipt_html(
        order_id="ORD-TEST1234",
        customer_name="Anjali",
        email="anjaliawasthi0908@gmail.com",
        payment_last4="4242",
        items=[_sample_product()],
        one_time_total=699,
        monthly_total=0,
        subtotal=699,
    )
    assert EVA_NAME in html
    assert EVA_EMAIL in html
    assert "Anjali" in html
    assert "<html" in html


def test_mask_email_hides_local_part():
    assert mask_email("anjaliawasthi0908@gmail.com") == "a***@gmail.com"


def test_eva_delivery_is_session_scoped(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.receipt_email_service.RECEIPTS_DIR", tmp_path)
    monkeypatch.setattr("app.services.receipt_email_service._send_to_inbox", lambda *_args, **_kwargs: (False, "outbox_only", None))
    result = deliver_receipt_via_eva(
        session_id="session-a",
        order_id="ORD-EVA1234",
        customer_name="Anjali",
        email="anjaliawasthi0908@gmail.com",
        payment_last4="4242",
        items=[_sample_product()],
        one_time_total=699,
        monthly_total=0,
        subtotal=699,
    )
    assert result["delivered"] is True
    assert result["from_email"] == EVA_EMAIL
    assert get_receipt_html("ORD-EVA1234", "session-a") is not None
    assert get_receipt_html("ORD-EVA1234", "session-b") is None
    meta_path = tmp_path / f"{__import__('hashlib').sha256(b'ORD-EVA1234').hexdigest()[:24]}.meta.json"
    assert meta_path.exists()
