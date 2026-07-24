import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
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


def chat(client, message, user_id, session_id):
    return client.post(
        "/api/chat",
        json={
            "message": message,
            "user_id": user_id,
            "session_id": session_id,
            "channel": "oneshop",
        },
    )


def proposal(client, user_id, session_id, message="Add Pixel 8"):
    response = chat(client, message, user_id, session_id)
    assert response.status_code == 200
    data = response.json()
    assert data["cart_updated"] is False
    assert data["cart_proposal"]
    return data


def confirm(client, user_id, session_id, proposal_id, key="confirm-key-123"):
    return client.post(
        "/api/chat/cart/confirm",
        json={
            "proposal_id": proposal_id,
            "idempotency_key": key,
            "session_id": session_id,
            "user_id": user_id,
            "channel": "oneshop",
        },
    )


def test_cart_lookup_tool_is_deterministic_grounded_and_exact(client, monkeypatch):
    user_id, session_id = identity()
    sid = chat(client, "Show my cart", user_id, session_id).json()["session_id"]
    session_store.add_bundle_to_cart(sid, ["google-pixel-8", "unlimited-plus"])

    async def should_not_parse(*_args, **_kwargs):
        raise AssertionError("cart lookup must not call the LLM parser")

    monkeypatch.setattr(shopassist, "_ai_parse", should_not_parse)
    response = chat(client, "What's in my cart and what is the cart total?", user_id, sid)
    data = response.json()

    assert response.status_code == 200
    assert data["selected_tool"] == "cart_lookup"
    assert data["cart_summary"]["total_items"] == 2
    assert data["cart_summary"]["one_time_total"] == 699
    assert data["cart_summary"]["monthly_total"] == 85
    assert [item["id"] for item in data["cart_summary"]["items"]] == [
        "google-pixel-8",
        "unlimited-plus",
    ]
    assert "$699.00 due once" in data["message"]
    assert "$85.00/month" in data["message"]
    assert "discount" not in data["message"].lower()


def test_tool_selection_issues_server_owned_single_and_bundle_proposals(client):
    user_id, session_id = identity()
    single = proposal(client, user_id, session_id)
    assert single["selected_tool"] == "propose_add_to_cart"
    assert single["actions"][0]["type"] == "PROPOSE_ADD_TO_CART"
    assert single["actions"][0]["proposal_id"] == single["cart_proposal"]["proposal_id"]
    assert single["cart_proposal"]["product_ids"] == ["google-pixel-8"]
    assert single["cart_proposal"]["one_time_total"] == 699
    assert single["cart_proposal"]["monthly_total"] == 0

    bundle = proposal(
        client,
        user_id,
        single["session_id"],
        "Add Pixel 8 and Unlimited Plus Plan under $90 as a bundle",
    )
    assert bundle["selected_tool"] == "propose_add_bundle"
    assert bundle["cart_proposal"]["product_ids"] == ["google-pixel-8", "unlimited-plus"]
    assert bundle["cart_proposal"]["one_time_total"] == 699
    assert bundle["cart_proposal"]["monthly_total"] == 85
    assert "cart is unchanged" in bundle["message"]


def test_confirmation_is_idempotent_and_never_duplicates_mutation(client, monkeypatch):
    user_id, session_id = identity()
    proposed = proposal(client, user_id, session_id)
    sid = proposed["session_id"]
    proposal_id = proposed["cart_proposal"]["proposal_id"]
    calls = 0
    original = session_store.add_bundle_to_cart

    def counted_add(target_sid, product_ids):
        nonlocal calls
        calls += 1
        return original(target_sid, product_ids)

    monkeypatch.setattr(session_store, "add_bundle_to_cart", counted_add)
    first = confirm(client, user_id, sid, proposal_id)
    same_key = confirm(client, user_id, sid, proposal_id)
    new_key = confirm(client, user_id, sid, proposal_id, "confirm-key-456")

    assert first.status_code == same_key.status_code == new_key.status_code == 200
    assert first.json()["added_product_ids"] == ["google-pixel-8"]
    assert same_key.json()["idempotent_replay"] is True
    assert new_key.json()["idempotent_replay"] is True
    assert calls == 1
    assert session_store.get_cart_ids(sid) == ["google-pixel-8"]


def test_confirmation_excludes_existing_items_and_computes_full_cart_totals(client):
    user_id, session_id = identity()
    initial = chat(client, "Show my cart", user_id, session_id).json()
    sid = initial["session_id"]
    session_store.add_to_cart(sid, "google-pixel-8")
    proposed = proposal(
        client,
        user_id,
        sid,
        "Add Pixel 8 and Unlimited Plus Plan under $90 as a bundle",
    )
    assert proposed["cart_proposal"]["excluded_product_ids"] == ["google-pixel-8"]

    result = confirm(
        client,
        user_id,
        sid,
        proposed["cart_proposal"]["proposal_id"],
    ).json()
    assert result["added_product_ids"] == ["unlimited-plus"]
    assert result["excluded_product_ids"] == ["google-pixel-8"]
    assert result["cart_summary"]["total_items"] == 2
    assert result["cart_summary"]["one_time_total"] == 699
    assert result["cart_summary"]["monthly_total"] == 85


def test_confirmation_fails_atomically_when_availability_or_price_changes(client):
    user_id, session_id = identity()
    proposed = proposal(
        client,
        user_id,
        session_id,
        "Add Pixel 8 and Unlimited Plus Plan under $90 as a bundle",
    )
    sid = proposed["session_id"]
    plan = catalog.get_by_id("unlimited-plus")
    assert plan
    original_stock = plan.in_stock
    try:
        plan.in_stock = False
        result = confirm(client, user_id, sid, proposed["cart_proposal"]["proposal_id"])
    finally:
        plan.in_stock = original_stock
    assert result.status_code == 409
    assert session_store.get_cart_ids(sid) == []

    changed = proposal(client, user_id, sid)
    pixel = catalog.get_by_id("google-pixel-8")
    assert pixel
    original_price = pixel.price
    try:
        pixel.price = original_price + 1
        result = confirm(
            client,
            user_id,
            sid,
            changed["cart_proposal"]["proposal_id"],
            "confirm-price-123",
        )
    finally:
        pixel.price = original_price
    assert result.status_code == 409
    assert "pricing changed" in result.json()["detail"]
    assert session_store.get_cart_ids(sid) == []


def test_proposals_are_isolated_across_users(client):
    owner, owner_session = identity()
    attacker, attacker_session = identity()
    proposed = proposal(client, owner, owner_session)

    attack = confirm(
        client,
        attacker,
        attacker_session,
        proposed["cart_proposal"]["proposal_id"],
    )
    assert attack.status_code == 409
    assert session_store.get_cart_ids(proposed["session_id"]) == []
    assert session_store.get_cart_ids(attacker_session) == []
