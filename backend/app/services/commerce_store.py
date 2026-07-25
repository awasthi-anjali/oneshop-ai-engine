from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import (
    CartConfirmationResponse,
    CartProposal,
    CartSummary,
    CheckoutReviewRequest,
    CheckoutReviewResponse,
    OrderReceipt,
    Product,
)
from app.services.product_catalog import catalog
from app.services.receipt_email_service import deliver_persisted_order_email


PROPOSAL_TTL_MINUTES = 15
REVIEW_TTL_MINUTES = 15


def commerce_error_detail(exc: ValueError) -> dict[str, str]:
    message = str(exc)
    lowered = message.lower()
    if message.startswith("SIMULATED_DECLINE"):
        code = "simulated_decline"
        message = message.partition(":")[2].strip() or "The demo card was declined."
    elif "disabled" in lowered:
        code = "ordering_disabled"
    elif "expired" in lowered:
        code = "expired_review"
    elif "cart changed" in lowered:
        code = "cart_changed"
    elif "pricing changed" in lowered:
        code = "price_changed"
    elif "no longer available" in lowered or "unavailable" in lowered:
        code = "unavailable_item"
    elif "idempotency key" in lowered:
        code = "idempotency_conflict"
    elif "token" in lowered:
        code = "invalid_confirmation"
    elif "belongs to another user" in lowered or "not found" in lowered:
        code = "owner_mismatch"
    elif "no longer active" in lowered or "cannot be cancelled" in lowered:
        code = "inactive_review"
    elif "empty" in lowered:
        code = "empty_cart"
    else:
        code = "validation_failed"
    return {"code": code, "message": message}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def minor_units(value: float) -> int:
    return int(
        (Decimal(str(value)) * Decimal("100")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _owner(user_id: str | None) -> str:
    return user_id or ""


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _snapshot_product(product: Product) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "name": product.name,
        "category": product.category.value,
        "currency": product.currency,
        "billing_period": product.billing_period,
        "unit_amount_minor": minor_units(product.price),
    }


def _totals(items: list[dict[str, Any]]) -> tuple[int, int]:
    one_time = sum(
        int(item["unit_amount_minor"])
        for item in items
        if item["billing_period"] != "monthly"
    )
    monthly = sum(
        int(item["unit_amount_minor"])
        for item in items
        if item["billing_period"] == "monthly"
    )
    return one_time, monthly


class CommerceStore:
    """Durable, single-instance commerce state for the hackathon deployment."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or settings.recommendation_db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=5,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA busy_timeout = 5000")
            if self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS commerce_carts (
                    session_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commerce_cart_items (
                    session_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, product_id),
                    FOREIGN KEY (session_id) REFERENCES commerce_carts(session_id)
                );
                CREATE TABLE IF NOT EXISTS commerce_cart_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    operation TEXT NOT NULL,
                    cart_version INTEGER NOT NULL,
                    product_ids_json TEXT NOT NULL,
                    excluded_ids_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    result_one_time_minor INTEGER NOT NULL,
                    result_monthly_minor INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS commerce_cart_confirmation_keys (
                    proposal_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (proposal_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS commerce_checkout_reviews (
                    review_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    cart_version INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    payment_token TEXT NOT NULL,
                    payment_last4 TEXT NOT NULL,
                    confirmation_token_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_order_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_checkout_reviews_session_status
                    ON commerce_checkout_reviews(session_id, status, expires_at);
                CREATE TABLE IF NOT EXISTS commerce_orders (
                    order_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    review_id TEXT NOT NULL UNIQUE,
                    customer_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    payment_token TEXT NOT NULL,
                    payment_last4 TEXT NOT NULL,
                    one_time_total_minor INTEGER NOT NULL,
                    monthly_total_minor INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commerce_order_items (
                    order_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    PRIMARY KEY (order_id, position)
                );
                CREATE TABLE IF NOT EXISTS commerce_order_idempotency (
                    session_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS commerce_order_events (
                    event_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commerce_email_outbox (
                    order_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    provider TEXT,
                    last_error TEXT,
                    sent_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES commerce_orders(order_id)
                );
                """
            )

    def _begin(self) -> None:
        self._conn.execute("BEGIN IMMEDIATE")

    def _ensure_cart_locked(self, session_id: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO commerce_carts(session_id, version, updated_at)
            VALUES (?, 0, ?)
            """,
            (session_id, utc_now().isoformat()),
        )

    def ensure_cart(self, session_id: str) -> None:
        with self._lock:
            self._ensure_cart_locked(session_id)

    def cart_version(self, session_id: str) -> int:
        with self._lock:
            self._ensure_cart_locked(session_id)
            row = self._conn.execute(
                "SELECT version FROM commerce_carts WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return int(row["version"])

    def cart_ids(self, session_id: str) -> list[str]:
        with self._lock:
            self._ensure_cart_locked(session_id)
            rows = self._conn.execute(
                """
                SELECT product_id FROM commerce_cart_items
                WHERE session_id = ? ORDER BY product_id
                """,
                (session_id,),
            ).fetchall()
            return [str(row["product_id"]) for row in rows]

    def _touch_cart_locked(self, session_id: str) -> None:
        self._conn.execute(
            """
            UPDATE commerce_carts
            SET version = version + 1, updated_at = ?
            WHERE session_id = ?
            """,
            (utc_now().isoformat(), session_id),
        )
        self._conn.execute(
            """
            UPDATE commerce_checkout_reviews SET status = 'stale'
            WHERE session_id = ? AND status = 'awaiting_confirmation'
            """,
            (session_id,),
        )

    def add_items(self, session_id: str, product_ids: list[str]) -> list[str]:
        with self._lock:
            self._begin()
            try:
                self._ensure_cart_locked(session_id)
                changed = False
                now = utc_now().isoformat()
                for product_id in product_ids:
                    if not catalog.get_by_id(product_id):
                        continue
                    cursor = self._conn.execute(
                        """
                        INSERT OR IGNORE INTO commerce_cart_items
                            (session_id, product_id, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (session_id, product_id, now),
                    )
                    changed = changed or cursor.rowcount == 1
                if changed:
                    self._touch_cart_locked(session_id)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return self.cart_ids(session_id)

    def remove_items(self, session_id: str, product_ids: list[str]) -> list[str]:
        with self._lock:
            self._begin()
            try:
                self._ensure_cart_locked(session_id)
                changed = False
                for product_id in product_ids:
                    cursor = self._conn.execute(
                        """
                        DELETE FROM commerce_cart_items
                        WHERE session_id = ? AND product_id = ?
                        """,
                        (session_id, product_id),
                    )
                    changed = changed or cursor.rowcount == 1
                if changed:
                    self._touch_cart_locked(session_id)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return self.cart_ids(session_id)

    def clear_cart(self, session_id: str) -> None:
        self.remove_items(session_id, self.cart_ids(session_id))

    def toggle_item(self, session_id: str, product_id: str) -> tuple[bool, list[str]]:
        if product_id in set(self.cart_ids(session_id)):
            return False, self.remove_items(session_id, [product_id])
        return True, self.add_items(session_id, [product_id])

    def merge_carts(self, source: str, target: str) -> None:
        self.add_items(target, self.cart_ids(source))

    def create_proposal(
        self,
        session_id: str,
        user_id: str | None,
        operation: str,
        product_ids: list[str],
    ) -> CartProposal:
        if operation not in {"add", "remove"}:
            raise ValueError("Unsupported cart operation.")
        with self._lock:
            products = catalog.get_by_ids(product_ids)
            if len(products) != len(product_ids) or any(not item.in_stock for item in products):
                raise ValueError("One or more requested items are unavailable.")
            current_ids = self.cart_ids(session_id)
            current_set = set(current_ids)
            if operation == "remove":
                product_ids = [
                    product_id for product_id in product_ids if product_id in current_set
                ]
                products = catalog.get_by_ids(product_ids)
                excluded = []
                if not product_ids:
                    raise ValueError("None of those items are in your cart.")
                remove_ids = set(product_ids)
                result_ids = [
                    product_id for product_id in current_ids if product_id not in remove_ids
                ]
            else:
                excluded = [product_id for product_id in product_ids if product_id in current_set]
                result_ids = list(dict.fromkeys([*current_ids, *product_ids]))
            result_items = [
                _snapshot_product(product) for product in catalog.get_by_ids(result_ids)
            ]
            result_one_time, result_monthly = _totals(result_items)
            item_snapshots = [_snapshot_product(product) for product in products]
            proposal_id = secrets.token_urlsafe(24)
            created = utc_now()
            expires = created + timedelta(minutes=PROPOSAL_TTL_MINUTES)
            one_time, monthly = _totals(item_snapshots)
            cart_version = self.cart_version(session_id)
            self._conn.execute(
                """
                INSERT INTO commerce_cart_proposals (
                    proposal_id, session_id, user_id, operation, cart_version,
                    product_ids_json, excluded_ids_json, snapshot_json,
                    result_one_time_minor, result_monthly_minor,
                    created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id,
                    session_id,
                    _owner(user_id),
                    operation,
                    cart_version,
                    json.dumps(product_ids),
                    json.dumps(excluded),
                    json.dumps(item_snapshots, sort_keys=True),
                    result_one_time,
                    result_monthly,
                    created.isoformat(),
                    expires.isoformat(),
                ),
            )
            return CartProposal(
                proposal_id=proposal_id,
                operation=operation,
                cart_version=cart_version,
                products=[product.model_copy(deep=True) for product in products],
                product_ids=product_ids,
                excluded_product_ids=excluded,
                one_time_total=one_time / 100,
                monthly_total=monthly / 100,
                resulting_one_time_total=result_one_time / 100,
                resulting_monthly_total=result_monthly / 100,
                expires_at=expires.isoformat(),
            )

    def confirm_proposal(
        self,
        proposal_id: str,
        idempotency_key: str,
        session_id: str,
        user_id: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            self._begin()
            try:
                row = self._conn.execute(
                    "SELECT * FROM commerce_cart_proposals WHERE proposal_id = ?",
                    (proposal_id,),
                ).fetchone()
                if (
                    not row
                    or str(row["session_id"]) != session_id
                    or str(row["user_id"]) != _owner(user_id)
                ):
                    raise ValueError("Cart proposal is missing, stale, or belongs to another user.")
                replay = self._conn.execute(
                    """
                    SELECT response_json FROM commerce_cart_confirmation_keys
                    WHERE proposal_id = ? AND idempotency_key = ?
                    """,
                    (proposal_id, idempotency_key),
                ).fetchone()
                if replay:
                    result = json.loads(str(replay["response_json"]))
                    result["idempotent_replay"] = True
                    self._conn.execute("COMMIT")
                    return result

                if int(row["consumed"]):
                    result = json.loads(str(row["result_json"]))
                    result["idempotent_replay"] = True
                else:
                    if datetime.fromisoformat(str(row["expires_at"])) <= utc_now():
                        raise ValueError("Cart proposal expired. Request a fresh proposal.")
                    self._ensure_cart_locked(session_id)
                    current_version = self._conn.execute(
                        "SELECT version FROM commerce_carts WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                    if int(current_version["version"]) != int(row["cart_version"]):
                        raise ValueError("Your cart changed. Request a fresh proposal.")
                    product_ids = json.loads(str(row["product_ids_json"]))
                    snapshots = json.loads(str(row["snapshot_json"]))
                    products = catalog.get_by_ids(product_ids)
                    if len(products) != len(product_ids) or any(not item.in_stock for item in products):
                        raise ValueError("One or more proposal items are no longer available.")
                    if [_snapshot_product(product) for product in products] != snapshots:
                        raise ValueError("Cart proposal pricing changed. Request a fresh proposal.")
                    existing = set(self.cart_ids(session_id))
                    operation = str(row["operation"])
                    if operation == "remove":
                        removed = [product_id for product_id in product_ids if product_id in existing]
                        added: list[str] = []
                        for product_id in removed:
                            self._conn.execute(
                                "DELETE FROM commerce_cart_items WHERE session_id = ? AND product_id = ?",
                                (session_id, product_id),
                            )
                    else:
                        added = [product_id for product_id in product_ids if product_id not in existing]
                        removed = []
                        now = utc_now().isoformat()
                        for product_id in added:
                            self._conn.execute(
                                """
                                INSERT INTO commerce_cart_items(session_id, product_id, created_at)
                                VALUES (?, ?, ?)
                                """,
                                (session_id, product_id, now),
                            )
                    if added or removed:
                        self._touch_cart_locked(session_id)
                    result = {
                        "session_id": session_id,
                        "proposal_id": proposal_id,
                        "cart_version": self.cart_version(session_id),
                        "operation": operation,
                        "added_product_ids": added,
                        "removed_product_ids": removed,
                        "excluded_product_ids": json.loads(str(row["excluded_ids_json"])),
                        "idempotent_replay": False,
                    }
                    self._conn.execute(
                        """
                        UPDATE commerce_cart_proposals
                        SET consumed = 1, result_json = ?
                        WHERE proposal_id = ?
                        """,
                        (json.dumps(result, sort_keys=True), proposal_id),
                    )
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO commerce_cart_confirmation_keys
                        (proposal_id, idempotency_key, response_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        proposal_id,
                        idempotency_key,
                        json.dumps(result, sort_keys=True),
                        utc_now().isoformat(),
                    ),
                )
                self._conn.execute("COMMIT")
                return result
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def create_review(self, request: CheckoutReviewRequest) -> CheckoutReviewResponse:
        if not settings.ordering_enabled or not settings.demo_payment_enabled:
            raise ValueError("Demo ordering is disabled.")
        if request.demo_payment_method.value == "demo_card_declined":
            raise ValueError("SIMULATED_DECLINE: Use the approved demo success card to continue.")
        with self._lock:
            self._begin()
            try:
                product_ids = self.cart_ids(request.session_id)
                products = catalog.get_by_ids(product_ids)
                if not products:
                    raise ValueError("Cart is empty.")
                if len(products) != len(product_ids) or any(
                    not product.in_stock for product in products
                ):
                    raise ValueError("One or more cart items are no longer available.")
                snapshots = [_snapshot_product(product) for product in products]
                one_time, monthly = _totals(snapshots)
                review_id = f"rev_{secrets.token_urlsafe(18)}"
                token = secrets.token_urlsafe(32)
                created = utc_now()
                expires = created + timedelta(minutes=REVIEW_TTL_MINUTES)
                cart_version = self.cart_version(request.session_id)
                self._conn.execute(
                    """
                    UPDATE commerce_checkout_reviews SET status = 'cancelled'
                    WHERE session_id = ? AND status = 'awaiting_confirmation'
                    """,
                    (request.session_id,),
                )
                self._conn.execute(
                    """
                    INSERT INTO commerce_checkout_reviews (
                        review_id, session_id, user_id, cart_version, snapshot_json,
                        customer_name, email, payment_token, payment_last4,
                        confirmation_token_hash, status, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        request.session_id,
                        _owner(request.user_id),
                        cart_version,
                        json.dumps(snapshots, sort_keys=True),
                        request.customer_name,
                        request.email,
                        request.demo_payment_method.value,
                        "4242",
                        _token_hash(token),
                        "awaiting_confirmation",
                        created.isoformat(),
                        expires.isoformat(),
                    ),
                )
                self._conn.execute("COMMIT")
                return CheckoutReviewResponse(
                    review_id=review_id,
                    session_id=request.session_id,
                    cart_version=cart_version,
                    status="awaiting_confirmation",
                    items=snapshots,
                    one_time_total_minor=one_time,
                    monthly_total_minor=monthly,
                    customer_name=request.customer_name,
                    email=request.email,
                    payment_last4="4242",
                    confirmation_token=token,
                    expires_at=expires.isoformat(),
                )
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def _review_response(self, row: sqlite3.Row) -> CheckoutReviewResponse:
        snapshots = json.loads(str(row["snapshot_json"]))
        one_time, monthly = _totals(snapshots)
        return CheckoutReviewResponse(
            review_id=str(row["review_id"]),
            session_id=str(row["session_id"]),
            cart_version=int(row["cart_version"]),
            status=str(row["status"]),
            items=snapshots,
            one_time_total_minor=one_time,
            monthly_total_minor=monthly,
            customer_name=str(row["customer_name"]),
            email=str(row["email"]),
            payment_last4=str(row["payment_last4"]),
            expires_at=str(row["expires_at"]),
            consumed_order_id=row["consumed_order_id"],
        )

    def get_review(
        self,
        review_id: str,
        session_id: str,
        user_id: str | None,
    ) -> CheckoutReviewResponse:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM commerce_checkout_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if (
            not row
            or str(row["session_id"]) != session_id
            or str(row["user_id"]) != _owner(user_id)
        ):
            raise ValueError("Checkout review was not found.")
        if (
            str(row["status"]) == "awaiting_confirmation"
            and datetime.fromisoformat(str(row["expires_at"])) <= utc_now()
        ):
            with self._lock:
                self._conn.execute(
                    """
                    UPDATE commerce_checkout_reviews SET status = 'expired'
                    WHERE review_id = ? AND status = 'awaiting_confirmation'
                    """,
                    (review_id,),
                )
                row = self._conn.execute(
                    "SELECT * FROM commerce_checkout_reviews WHERE review_id = ?",
                    (review_id,),
                ).fetchone()
        return self._review_response(row)

    def cancel_review(self, review_id: str, session_id: str, user_id: str | None) -> None:
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE commerce_checkout_reviews SET status = 'cancelled'
                WHERE review_id = ? AND session_id = ? AND user_id = ?
                  AND status = 'awaiting_confirmation'
                """,
                (review_id, session_id, _owner(user_id)),
            )
        if cursor.rowcount != 1:
            raise ValueError("Checkout review cannot be cancelled.")

    def place_order(
        self,
        review_id: str,
        confirmation_token: str,
        idempotency_key: str,
        session_id: str,
        user_id: str | None,
    ) -> OrderReceipt:
        with self._lock:
            self._begin()
            try:
                replay = self._conn.execute(
                    """
                    SELECT i.order_id, o.review_id
                    FROM commerce_order_idempotency i
                    JOIN commerce_orders o ON o.order_id = i.order_id
                    WHERE i.session_id = ? AND i.idempotency_key = ?
                      AND o.user_id = ?
                    """,
                    (session_id, idempotency_key, _owner(user_id)),
                ).fetchone()
                if replay:
                    if str(replay["review_id"]) != review_id:
                        raise ValueError("Idempotency key was already used for another checkout review.")
                    receipt = self._order_receipt_locked(str(replay["order_id"]))
                    self._conn.execute("COMMIT")
                    receipt = self._deliver_order_email(receipt.order_id)
                    return receipt.model_copy(update={"idempotent_replay": True})
                if not settings.ordering_enabled or not settings.demo_payment_enabled:
                    raise ValueError("Demo ordering is disabled.")
                row = self._conn.execute(
                    "SELECT * FROM commerce_checkout_reviews WHERE review_id = ?",
                    (review_id,),
                ).fetchone()
                if (
                    not row
                    or str(row["session_id"]) != session_id
                    or str(row["user_id"]) != _owner(user_id)
                ):
                    raise ValueError("Checkout review is missing or belongs to another user.")
                if not secrets.compare_digest(
                    str(row["confirmation_token_hash"]),
                    _token_hash(confirmation_token),
                ):
                    raise ValueError("Checkout confirmation token is invalid.")
                if row["consumed_order_id"]:
                    receipt = self._order_receipt_locked(str(row["consumed_order_id"]))
                    self._conn.execute(
                        """
                        INSERT OR IGNORE INTO commerce_order_idempotency
                            (session_id, idempotency_key, order_id, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (session_id, idempotency_key, receipt.order_id, utc_now().isoformat()),
                    )
                    self._conn.execute("COMMIT")
                    receipt = self._deliver_order_email(receipt.order_id)
                    return receipt.model_copy(update={"idempotent_replay": True})
                if str(row["status"]) != "awaiting_confirmation":
                    raise ValueError("Checkout review is no longer active.")
                if datetime.fromisoformat(str(row["expires_at"])) <= utc_now():
                    raise ValueError("Checkout review expired. Create a fresh review.")
                current_version = self._conn.execute(
                    "SELECT version FROM commerce_carts WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if not current_version or int(current_version["version"]) != int(row["cart_version"]):
                    raise ValueError("Your cart changed. Create a fresh checkout review.")
                snapshots = json.loads(str(row["snapshot_json"]))
                product_ids = [str(item["product_id"]) for item in snapshots]
                products = catalog.get_by_ids(product_ids)
                if len(products) != len(product_ids) or any(not product.in_stock for product in products):
                    raise ValueError("One or more order items are no longer available.")
                if [_snapshot_product(product) for product in products] != snapshots:
                    raise ValueError("Order pricing changed. Create a fresh checkout review.")
                one_time, monthly = _totals(snapshots)
                order_id = f"ORD-{uuid.uuid4().hex[:10].upper()}"
                created_at = utc_now().isoformat()
                self._conn.execute(
                    """
                    INSERT INTO commerce_orders (
                        order_id, session_id, user_id, review_id, customer_name,
                        email, payment_token, payment_last4,
                        one_time_total_minor, monthly_total_minor, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        session_id,
                        _owner(user_id),
                        review_id,
                        str(row["customer_name"]),
                        str(row["email"]),
                        str(row["payment_token"]),
                        str(row["payment_last4"]),
                        one_time,
                        monthly,
                        "demo_order_confirmed",
                        created_at,
                    ),
                )
                for position, snapshot in enumerate(snapshots):
                    self._conn.execute(
                        """
                        INSERT INTO commerce_order_items(order_id, position, snapshot_json)
                        VALUES (?, ?, ?)
                        """,
                        (order_id, position, json.dumps(snapshot, sort_keys=True)),
                    )
                self._conn.execute(
                    """
                    INSERT INTO commerce_order_idempotency
                        (session_id, idempotency_key, order_id, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (session_id, idempotency_key, order_id, created_at),
                )
                self._conn.execute(
                    """
                    INSERT INTO commerce_order_events(event_id, order_id, event_type, created_at)
                    VALUES (?, ?, 'demo_order_confirmed', ?)
                    """,
                    (uuid.uuid4().hex, order_id, created_at),
                )
                self._conn.execute(
                    """
                    INSERT INTO commerce_email_outbox(order_id, status, attempts, updated_at)
                    VALUES (?, 'pending', 0, ?)
                    """,
                    (order_id, created_at),
                )
                self._conn.execute(
                    """
                    UPDATE commerce_checkout_reviews
                    SET status = 'consumed', consumed_order_id = ?
                    WHERE review_id = ?
                    """,
                    (order_id, review_id),
                )
                self._conn.execute(
                    "DELETE FROM commerce_cart_items WHERE session_id = ?",
                    (session_id,),
                )
                self._touch_cart_locked(session_id)
                receipt = self._order_receipt_locked(order_id)
                self._conn.execute("COMMIT")
                return self._deliver_order_email(receipt.order_id)
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def _order_receipt_locked(self, order_id: str) -> OrderReceipt:
        order = self._conn.execute(
            "SELECT * FROM commerce_orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if not order:
            raise ValueError("Order was not found.")
        item_rows = self._conn.execute(
            """
            SELECT snapshot_json FROM commerce_order_items
            WHERE order_id = ? ORDER BY position
            """,
            (order_id,),
        ).fetchall()
        email_row = self._conn.execute(
            "SELECT status, attempts, provider FROM commerce_email_outbox WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        return OrderReceipt(
            order_id=str(order["order_id"]),
            session_id=str(order["session_id"]),
            status=str(order["status"]),
            payment_last4=str(order["payment_last4"]),
            customer_name=str(order["customer_name"]),
            email=str(order["email"]),
            items=[json.loads(str(item["snapshot_json"])) for item in item_rows],
            one_time_total_minor=int(order["one_time_total_minor"]),
            monthly_total_minor=int(order["monthly_total_minor"]),
            created_at=str(order["created_at"]),
            email_status=str(email_row["status"]) if email_row else "pending",
            email_attempts=int(email_row["attempts"]) if email_row else 0,
            email_provider=str(email_row["provider"]) if email_row and email_row["provider"] else None,
        )

    def _deliver_order_email(self, order_id: str) -> OrderReceipt:
        """Claim one outbox attempt and deliver only from the persisted receipt."""
        row = self._conn.execute(
            "SELECT status FROM commerce_email_outbox WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if not row or str(row["status"]) in {"sent", "sending"}:
            return self._order_receipt_locked(order_id)
        now = utc_now().isoformat()
        claimed = self._conn.execute(
            """
            UPDATE commerce_email_outbox
            SET status = 'sending', attempts = attempts + 1, updated_at = ?
            WHERE order_id = ? AND status IN ('pending', 'failed')
            """,
            (now, order_id),
        )
        if claimed.rowcount != 1:
            return self._order_receipt_locked(order_id)
        receipt = self._order_receipt_locked(order_id)
        try:
            result = deliver_persisted_order_email(receipt)
            delivered = bool(result["delivered"])
            status = "sent" if delivered else "failed"
            provider = str(result.get("provider") or "outbox_only")
            error = None if delivered else str(result.get("error") or "provider_not_configured")
        except Exception as exc:
            status = "failed"
            provider = None
            error = type(exc).__name__
        self._conn.execute(
            """
            UPDATE commerce_email_outbox
            SET status = ?, provider = ?, last_error = ?, sent_at = ?, updated_at = ?
            WHERE order_id = ?
            """,
            (status, provider, error, now if status == "sent" else None, now, order_id),
        )
        return self._order_receipt_locked(order_id)

    def get_order(self, order_id: str, session_id: str, user_id: str | None) -> OrderReceipt:
        with self._lock:
            row = self._conn.execute(
                "SELECT session_id, user_id FROM commerce_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if (
                not row
                or str(row["session_id"]) != session_id
                or str(row["user_id"]) != _owner(user_id)
            ):
                raise ValueError("Order was not found.")
            return self._order_receipt_locked(order_id)

    def get_order_by_idempotency(
        self,
        key: str,
        session_id: str,
        user_id: str | None,
    ) -> OrderReceipt:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT i.order_id
                FROM commerce_order_idempotency i
                JOIN commerce_orders o ON o.order_id = i.order_id
                WHERE i.session_id = ? AND i.idempotency_key = ? AND o.user_id = ?
                """,
                (session_id, key, _owner(user_id)),
            ).fetchone()
            if not row:
                raise ValueError("Order was not found.")
            return self._order_receipt_locked(str(row["order_id"]))

    def close(self) -> None:
        with self._lock:
            self._conn.close()


commerce_store = CommerceStore()
