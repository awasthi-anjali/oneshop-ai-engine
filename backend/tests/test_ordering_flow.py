import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.commerce_store import CommerceStore, commerce_store
from app.services.product_catalog import catalog
from app.services.session_store import session_store
from app.services.shopassist_service import shopassist


@pytest.fixture(autouse=True)
def deterministic_mode(monkeypatch):
    monkeypatch.setattr(shopassist, "_client", None)


@pytest.fixture
def client():
    return TestClient(app)


def identity() -> tuple[str, str]:
    token = uuid.uuid4().hex
    return f"user_{token}", f"session_{token}"


def chat(client, message, user_id, session_id, checkout_confirmation=None):
    payload = {
        "message": message,
        "user_id": user_id,
        "session_id": session_id,
        "channel": "oneshop",
    }
    if checkout_confirmation:
        payload["checkout_confirmation"] = checkout_confirmation
    return client.post("/api/chat", json=payload)


def resolved_session(client, user_id, session_id):
    return chat(client, "Show my cart", user_id, session_id).json()["session_id"]


def review(client, user_id, session_id, payment="demo_card_success"):
    return client.post(
        "/api/checkout/reviews",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "customer_name": "Demo Customer",
            "email": "demo@example.com",
            "demo_payment_method": payment,
        },
    )


def test_remove_item_and_remove_all_require_explicit_confirmation(client):
    user_id, initial = identity()
    sid = resolved_session(client, user_id, initial)
    session_store.add_bundle_to_cart(sid, ["google-pixel-8", "unlimited-plus"])

    proposed = chat(
        client,
        "Remove Unlimited Plus Plan from my cart",
        user_id,
        sid,
    ).json()
    assert proposed["selected_tool"] == "propose_remove_from_cart"
    assert proposed["cart_proposal"]["operation"] == "remove"
    assert proposed["cart_proposal"]["product_ids"] == ["unlimited-plus"]
    assert set(session_store.get_cart_ids(sid)) == {"google-pixel-8", "unlimited-plus"}

    confirmed = client.post(
        "/api/chat/cart/confirm",
        json={
            "proposal_id": proposed["cart_proposal"]["proposal_id"],
            "idempotency_key": "remove-plan-123",
            "session_id": sid,
            "user_id": user_id,
            "channel": "oneshop",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["operation"] == "remove"
    assert confirmed.json()["removed_product_ids"] == ["unlimited-plus"]
    assert session_store.get_cart_ids(sid) == ["google-pixel-8"]

    remove_all = chat(client, "Clear my cart", user_id, sid).json()
    assert remove_all["cart_proposal"]["product_ids"] == ["google-pixel-8"]
    assert session_store.get_cart_ids(sid) == ["google-pixel-8"]


def test_remove_proposal_is_owner_bound_and_stale_after_cart_change(client):
    owner, initial = identity()
    attacker, attacker_initial = identity()
    sid = resolved_session(client, owner, initial)
    attacker_sid = resolved_session(client, attacker, attacker_initial)
    session_store.add_bundle_to_cart(sid, ["google-pixel-8", "unlimited-plus"])
    proposed = chat(client, "Clear my cart", owner, sid).json()["cart_proposal"]

    attack = client.post(
        "/api/chat/cart/confirm",
        json={
            "proposal_id": proposed["proposal_id"],
            "idempotency_key": "attack-remove-123",
            "session_id": attacker_sid,
            "user_id": attacker,
        },
    )
    assert attack.status_code == 409
    session_store.remove_from_cart(sid, "unlimited-plus")
    stale = client.post(
        "/api/chat/cart/confirm",
        json={
            "proposal_id": proposed["proposal_id"],
            "idempotency_key": "stale-remove-123",
            "session_id": sid,
            "user_id": owner,
        },
    )
    assert stale.status_code == 409
    assert session_store.get_cart_ids(sid) == ["google-pixel-8"]


def test_consumed_proposal_replay_stays_owner_bound(client):
    owner, initial = identity()
    attacker, attacker_initial = identity()
    sid = resolved_session(client, owner, initial)
    attacker_sid = resolved_session(client, attacker, attacker_initial)
    session_store.add_to_cart(sid, "google-pixel-8")
    proposed = chat(client, "Clear my cart", owner, sid).json()["cart_proposal"]
    payload = {
        "proposal_id": proposed["proposal_id"],
        "idempotency_key": "owner-replay-123",
        "session_id": sid,
        "user_id": owner,
    }
    assert client.post("/api/chat/cart/confirm", json=payload).status_code == 200

    attack = client.post(
        "/api/chat/cart/confirm",
        json={
            **payload,
            "session_id": attacker_sid,
            "user_id": attacker,
        },
    )
    assert attack.status_code == 409
    assert attack.json()["detail"]["code"] == "owner_mismatch"


def test_review_accepts_only_demo_tokens_and_rejects_raw_card_fields(client):
    user_id, initial = identity()
    sid = resolved_session(client, user_id, initial)
    session_store.add_to_cart(sid, "google-pixel-8")

    declined = review(client, user_id, sid, "demo_card_declined")
    assert declined.status_code == 402
    assert declined.json()["detail"]["code"] == "simulated_decline"
    assert declined.json()["detail"]["message"] == (
        "Use the approved demo success card to continue."
    )

    raw_card = client.post(
        "/api/checkout/reviews",
        json={
            "session_id": sid,
            "user_id": user_id,
            "customer_name": "Demo Customer",
            "email": "demo@example.com",
            "demo_payment_method": "demo_card_success",
            "card_number": "4242424242424242",
            "cvc": "123",
        },
    )
    assert raw_card.status_code == 422

    created = review(client, user_id, sid)
    assert created.status_code == 200
    payload = created.json()
    assert payload["payment_last4"] == "4242"
    assert payload["payment_mode"] == "demo_simulated"
    assert "4242424242424242" not in json.dumps(payload)


def test_natural_confirmation_creates_one_durable_order(client):
    user_id, initial = identity()
    sid = resolved_session(client, user_id, initial)
    session_store.add_bundle_to_cart(sid, ["google-pixel-8", "unlimited-plus"])
    created = review(client, user_id, sid).json()
    context = {
        "review_id": created["review_id"],
        "confirmation_token": created["confirmation_token"],
        "idempotency_key": "place-order-123",
    }

    unscoped_yes = chat(client, "yes", user_id, sid)
    assert unscoped_yes.status_code == 200
    assert unscoped_yes.json()["order_receipt"] is None
    assert set(session_store.get_cart_ids(sid)) == {"google-pixel-8", "unlimited-plus"}

    compound = chat(client, "yes, but remove the plan", user_id, sid, context)
    assert compound.status_code == 200
    assert compound.json()["order_receipt"] is None
    assert set(session_store.get_cart_ids(sid)) == {"google-pixel-8", "unlimited-plus"}

    placed = chat(client, "yes", user_id, sid, context)
    assert placed.status_code == 200
    receipt = placed.json()["order_receipt"]
    assert receipt["status"] == "demo_order_confirmed"
    assert receipt["payment_status"] == "simulated"
    assert receipt["one_time_total_minor"] == 69900
    assert receipt["monthly_total_minor"] == 8500
    assert session_store.get_cart_ids(sid) == []

    replay = chat(client, "confirm", user_id, sid, context).json()["order_receipt"]
    assert replay["order_id"] == receipt["order_id"]
    assert replay["idempotent_replay"] is True

    fetched = client.get(
        f"/api/orders/{receipt['order_id']}",
        params={"session_id": sid, "user_id": user_id},
    )
    assert fetched.status_code == 200
    assert fetched.json()["items"][0]["unit_amount_minor"] in {69900, 8500}

    reopened = CommerceStore(commerce_store.db_path)
    try:
        persisted = reopened.get_order(receipt["order_id"], sid, user_id)
        assert persisted.order_id == receipt["order_id"]
        assert persisted.one_time_total_minor == 69900
    finally:
        reopened.close()


def test_concurrent_confirmation_keys_create_one_order(client):
    user_id, initial = identity()
    sid = resolved_session(client, user_id, initial)
    session_store.add_to_cart(sid, "google-pixel-8")
    created = review(client, user_id, sid).json()

    def place(key):
        return commerce_store.place_order(
            created["review_id"],
            created["confirmation_token"],
            key,
            sid,
            user_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(place, ["concurrent-order-a", "concurrent-order-b"]))
    assert len({receipt.order_id for receipt in receipts}) == 1
    assert session_store.get_cart_ids(sid) == []


def test_cart_proposal_and_idempotency_survive_store_restart(tmp_path):
    db_path = tmp_path / "commerce.sqlite3"
    first = CommerceStore(db_path)
    sid = "restart-session"
    user_id = "restart-user"
    first.add_items(sid, ["google-pixel-8", "unlimited-plus"])
    proposal = first.create_proposal(sid, user_id, "remove", ["unlimited-plus"])
    first.close()

    second = CommerceStore(db_path)
    try:
        result = second.confirm_proposal(
            proposal.proposal_id,
            "restart-remove-key",
            sid,
            user_id,
        )
        replay = second.confirm_proposal(
            proposal.proposal_id,
            "restart-remove-key",
            sid,
            user_id,
        )
        assert result["removed_product_ids"] == ["unlimited-plus"]
        assert replay["idempotent_replay"] is True
        assert second.cart_ids(sid) == ["google-pixel-8"]
    finally:
        second.close()


def test_cancel_and_changed_cart_create_no_order(client):
    user_id, initial = identity()
    sid = resolved_session(client, user_id, initial)
    session_store.add_to_cart(sid, "google-pixel-8")
    created = review(client, user_id, sid).json()
    context = {
        "review_id": created["review_id"],
        "confirmation_token": created["confirmation_token"],
        "idempotency_key": "cancel-order-123",
    }
    cancelled = chat(client, "no", user_id, sid, context)
    assert cancelled.status_code == 200
    assert cancelled.json()["checkout_review_status"] == "cancelled"
    assert session_store.get_cart_ids(sid) == ["google-pixel-8"]
    assert client.get(
        "/api/orders/by-idempotency/cancel-order-123",
        params={"session_id": sid, "user_id": user_id},
    ).status_code == 404

    changed_review = review(client, user_id, sid).json()
    session_store.add_to_cart(sid, "unlimited-plus")
    changed = chat(
        client,
        "yes",
        user_id,
        sid,
        {
            "review_id": changed_review["review_id"],
            "confirmation_token": changed_review["confirmation_token"],
            "idempotency_key": "changed-order-123",
        },
    )
    assert changed.status_code == 422
    assert set(session_store.get_cart_ids(sid)) == {"google-pixel-8", "unlimited-plus"}


def test_catalog_price_change_rejects_order_without_clearing_cart(client):
    user_id, initial = identity()
    sid = resolved_session(client, user_id, initial)
    session_store.add_to_cart(sid, "google-pixel-8")
    created = review(client, user_id, sid).json()
    pixel = catalog.get_by_id("google-pixel-8")
    assert pixel
    original = pixel.price
    try:
        pixel.price = original + 1
        response = chat(
            client,
            "place order",
            user_id,
            sid,
            {
                "review_id": created["review_id"],
                "confirmation_token": created["confirmation_token"],
                "idempotency_key": "price-order-123",
            },
        )
    finally:
        pixel.price = original
    assert response.status_code == 422
    assert session_store.get_cart_ids(sid) == ["google-pixel-8"]


def test_catalog_availability_change_rejects_order_without_clearing_cart(client):
    user_id, initial = identity()
    sid = resolved_session(client, user_id, initial)
    session_store.add_to_cart(sid, "google-pixel-8")
    created = review(client, user_id, sid).json()
    pixel = catalog.get_by_id("google-pixel-8")
    assert pixel
    try:
        pixel.in_stock = False
        response = chat(
            client,
            "confirm",
            user_id,
            sid,
            {
                "review_id": created["review_id"],
                "confirmation_token": created["confirmation_token"],
                "idempotency_key": "availability-order-123",
            },
        )
    finally:
        pixel.in_stock = True
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unavailable_item"
    assert session_store.get_cart_ids(sid) == ["google-pixel-8"]


def test_database_does_not_store_raw_card_or_confirmation_token(client):
    user_id, initial = identity()
    sid = resolved_session(client, user_id, initial)
    session_store.add_to_cart(sid, "google-pixel-8")
    created = review(client, user_id, sid).json()
    with sqlite3.connect(commerce_store.db_path) as connection:
        dump = "\n".join(connection.iterdump())
    assert "4242424242424242" not in dump
    assert created["confirmation_token"] not in dump
