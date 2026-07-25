"""Eva — HTML receipt delivery to the customer's real inbox."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path

from urllib.parse import quote

import httpx

from app.config import settings
from app.models.schemas import Product, ProductCategory

logger = logging.getLogger(__name__)

EVA_NAME = "Eva"
EVA_EMAIL = "eva@gmail.com"
EVA_FROM = f"{EVA_NAME} <{EVA_EMAIL}>"

RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "data" / "receipts"
_order_sessions: dict[str, str] = {}


def mask_email(email: str) -> str:
    trimmed = email.strip()
    if "@" not in trimmed:
        return "***"
    local, domain = trimmed.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = f"{local[0]}***"
    return f"{masked_local}@{domain}"


def _receipt_digest(order_id: str) -> str:
    return hashlib.sha256(order_id.encode("utf-8")).hexdigest()[:24]


def _receipt_path(order_id: str) -> Path:
    return RECEIPTS_DIR / f"{_receipt_digest(order_id)}.html"


def _receipt_meta_path(order_id: str) -> Path:
    return RECEIPTS_DIR / f"{_receipt_digest(order_id)}.meta.json"


def _link_receipt_session(order_id: str, session_id: str) -> None:
    _order_sessions[order_id] = session_id
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    _receipt_meta_path(order_id).write_text(
        json.dumps({"order_id": order_id, "session_id": session_id}),
        encoding="utf-8",
    )


def _resolve_receipt_session(order_id: str) -> str | None:
    cached = _order_sessions.get(order_id)
    if cached:
        return cached
    meta_path = _receipt_meta_path(order_id)
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    session_id = data.get("session_id")
    if isinstance(session_id, str) and session_id:
        _order_sessions[order_id] = session_id
        return session_id
    return None


def _format_money(amount: float, monthly: bool = False) -> str:
    suffix = "/month" if monthly else ""
    return f"${amount:,.2f}{suffix}"


def render_receipt_html(
    *,
    order_id: str,
    customer_name: str,
    email: str,
    payment_last4: str,
    items: list[Product],
    one_time_total: float,
    monthly_total: float,
    subtotal: float,
) -> str:
    rows: list[str] = []
    for item in items:
        monthly = item.category == ProductCategory.PLAN
        price = _format_money(item.price, monthly=monthly)
        rows.append(
            "<tr>"
            f"<td style=\"padding:12px;border-bottom:1px solid #e5e7eb;\">{escape(item.name)}</td>"
            f"<td style=\"padding:12px;border-bottom:1px solid #e5e7eb;\">{escape(item.brand)}</td>"
            f"<td style=\"padding:12px;border-bottom:1px solid #e5e7eb;text-align:right;\">{price}</td>"
            "</tr>"
        )

    placed_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    summary_rows = []
    if one_time_total > 0:
        summary_rows.append(
            f"<tr><td>Due once</td><td style=\"text-align:right;\">{_format_money(one_time_total)}</td></tr>"
        )
    if monthly_total > 0:
        summary_rows.append(
            f"<tr><td>Monthly service</td><td style=\"text-align:right;\">{_format_money(monthly_total, monthly=True)}</td></tr>"
        )
    summary_rows.append(
        f"<tr><td><strong>Catalog subtotal</strong></td>"
        f"<td style=\"text-align:right;\"><strong>{_format_money(subtotal)}</strong></td></tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OneShop Receipt {escape(order_id)}</title>
</head>
<body style="margin:0;padding:24px;background:#f3f4f6;font-family:Arial,sans-serif;color:#111827;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,0.08);">
    <tr>
      <td style="padding:28px 32px;background:linear-gradient(135deg,#111827,#2563eb);color:#ffffff;">
        <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.85;">OneShop · from {escape(EVA_NAME)}</div>
        <h1 style="margin:8px 0 0;font-size:28px;">Order confirmed</h1>
        <p style="margin:8px 0 0;font-size:15px;opacity:0.92;">Hi {escape(customer_name)}, your receipt is ready.</p>
      </td>
    </tr>
    <tr>
      <td style="padding:28px 32px;">
        <p style="margin:0 0 20px;font-size:14px;color:#374151;">
          Sent by <strong>{escape(EVA_NAME)}</strong>
          (<a href="mailto:{escape(EVA_EMAIL)}" style="color:#2563eb;">{escape(EVA_EMAIL)}</a>)
          on behalf of OneShop.
        </p>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:24px;">
          <tr>
            <td style="padding-bottom:8px;"><strong>Order ID</strong><br />{escape(order_id)}</td>
            <td style="padding-bottom:8px;text-align:right;"><strong>Placed</strong><br />{placed_at}</td>
          </tr>
          <tr>
            <td colspan="2" style="padding-top:8px;"><strong>Delivered to</strong><br />{escape(email)}</td>
          </tr>
          <tr>
            <td colspan="2" style="padding-top:8px;"><strong>Payment</strong><br />Card ending in {escape(payment_last4)}</td>
          </tr>
        </table>

        <h2 style="margin:0 0 12px;font-size:18px;">Items</h2>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin-bottom:24px;">
          <thead>
            <tr style="background:#f9fafb;">
              <th align="left" style="padding:12px;border-bottom:1px solid #e5e7eb;">Product</th>
              <th align="left" style="padding:12px;border-bottom:1px solid #e5e7eb;">Brand</th>
              <th align="right" style="padding:12px;border-bottom:1px solid #e5e7eb;">Price</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>

        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-top:2px solid #111827;padding-top:12px;">
          {''.join(summary_rows)}
        </table>

        <p style="margin:24px 0 0;font-size:13px;color:#6b7280;">
          Demo receipt — no real payment was processed.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_via_eva_gmail(to_email: str, subject: str, html: str) -> bool:
    if not settings.eva_gmail_enabled:
        return False
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = EVA_FROM
    message["To"] = to_email
    message["Reply-To"] = EVA_EMAIL
    message.attach(MIMEText(f"Your OneShop order receipt. Open the HTML version in a modern mail client.", "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(EVA_EMAIL, settings.eva_gmail_app_password)
            server.sendmail(EVA_EMAIL, [to_email], message.as_string())
        logger.info("Eva Gmail delivered receipt to %s", mask_email(to_email))
        return True
    except Exception as exc:
        logger.warning("Eva Gmail delivery failed for %s: %s", mask_email(to_email), type(exc).__name__)
        return False


def _send_via_resend(to_email: str, subject: str, html: str) -> tuple[bool, str | None]:
    if not settings.resend_enabled:
        return False, None
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from,
                "to": [to_email],
                "reply_to": EVA_EMAIL,
                "subject": subject,
                "html": html,
            },
            timeout=30.0,
        )
        if response.status_code in {200, 201}:
            logger.info("Resend delivered receipt to %s", mask_email(to_email))
            return True, None
        body = response.text[:400]
        logger.warning("Resend failed (%s): %s", response.status_code, body)
        if response.status_code == 403 and "only send testing emails to your own email address" in body:
            return False, "resend_sandbox_recipient"
        return False, "resend_failed"
    except Exception as exc:
        logger.warning("Resend delivery failed: %s", type(exc).__name__)
        return False, "resend_failed"


def _send_to_inbox(to_email: str, order_id: str, html: str) -> tuple[bool, str, str | None]:
    subject = f"Your OneShop receipt — {order_id}"
    if _send_via_eva_gmail(to_email, subject, html):
        return True, "gmail", None
    sent, resend_error = _send_via_resend(to_email, subject, html)
    if sent:
        return True, "resend", None
    return False, "outbox_only", resend_error


def deliver_receipt_via_eva(
    *,
    session_id: str,
    order_id: str,
    customer_name: str,
    email: str,
    payment_last4: str,
    items: list[Product],
    one_time_total: float,
    monthly_total: float,
    subtotal: float,
) -> dict[str, str | bool]:
    html = render_receipt_html(
        order_id=order_id,
        customer_name=customer_name,
        email=email,
        payment_last4=payment_last4,
        items=items,
        one_time_total=one_time_total,
        monthly_total=monthly_total,
        subtotal=subtotal,
    )
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _receipt_path(order_id)
    path.write_text(html, encoding="utf-8")
    _link_receipt_session(order_id, session_id)

    inbox_delivered, delivery_method, delivery_error = _send_to_inbox(email, order_id, html)
    masked = mask_email(email)
    logger.info(
        "Eva receipt for order %s -> %s (method=%s, inbox=%s)",
        order_id,
        masked,
        delivery_method,
        inbox_delivered,
    )
    return {
        "delivered": True,
        "inbox_delivered": inbox_delivered,
        "delivery_method": delivery_method,
        "delivery_error": delivery_error,
        "from": EVA_FROM,
        "from_name": EVA_NAME,
        "from_email": EVA_EMAIL,
        "to_masked": masked,
    }


def get_receipt_html(order_id: str, session_id: str) -> str | None:
    linked_session = _resolve_receipt_session(order_id)
    if not linked_session or linked_session != session_id:
        return None
    path = _receipt_path(order_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def receipt_view_path(order_id: str, session_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9-]", "", order_id)
    return f"/api/checkout/receipt/{safe_id}?session_id={quote(session_id, safe='')}"
