import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.commerce_store import commerce_store
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


def test_cart_lookup_is_backend_grounded_exact_and_does_not_require_ai(client):
    user_id, session_id = identity()
    sid = chat(client, "Show my cart", user_id, session_id).json()["session_id"]
    session_store.add_bundle_to_cart(sid, ["google-pixel-8", "unlimited-plus"])

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
    assert data["mode"] == "fallback"


def test_typo_cart_lookup_overrides_bad_ai_service_route(client, monkeypatch):
    user_id, session_id = identity()
    sid = chat(client, "Show my cart", user_id, session_id).json()["session_id"]
    session_store.add_bundle_to_cart(sid, ["google-pixel-8", "unlimited-plus"])

    async def misclassified(*_args, **_kwargs):
        return {
            "intent": "service",
            "goal": "converse",
            "scope": "retain",
        }

    monkeypatch.setattr(shopassist, "_ai_parse", misclassified)
    data = chat(client, "whatz in my cart?", user_id, sid).json()

    assert data["status"] == "recommended"
    assert data["selected_tool"] == "cart_lookup"
    assert data["cart_summary"]["total_items"] == 2
    assert "customer support" not in data["message"].lower()


@pytest.mark.parametrize("message", ["place the order", "confirm the order", "check out"])
def test_order_intent_opens_trusted_checkout_without_creating_order(client, message):
    user_id, session_id = identity()
    sid = chat(client, "Show my cart", user_id, session_id).json()["session_id"]
    session_store.add_to_cart(sid, "google-pixel-8")

    data = chat(client, message, user_id, sid).json()

    assert data["status"] == "recommended"
    assert data["selected_tool"] == "checkout"
    assert data["open_checkout"] is True
    assert data["cart_summary"]["total_items"] == 1
    assert data["order_receipt"] is None
    assert session_store.get_cart_ids(sid) == ["google-pixel-8"]


def test_order_intent_with_empty_cart_does_not_open_checkout_or_create_order(client):
    user_id, session_id = identity()

    data = chat(client, "place the order", user_id, session_id).json()

    assert data["status"] == "no_match"
    assert data["selected_tool"] == "checkout"
    assert data["open_checkout"] is False
    assert data["cart_summary"]["total_items"] == 0
    assert data["order_receipt"] is None


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


def test_ai_interprets_named_add_before_budget_clarification(client, monkeypatch):
    user_id, session_id = identity()

    async def select_named_add(*_args, **_kwargs):
        return {
            "intent": "shopping",
            "goal": "cart_add",
            "scope": "retain",
            "product_ids": ["google-pixel-8", "unlimited-plus"],
        }

    monkeypatch.setattr(shopassist, "_ai_parse", select_named_add)
    response = chat(
        client,
        "Add Google Pixel 8 and Unlimited Plus Plan to my cart",
        user_id,
        session_id,
    )
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "recommended"
    assert data["selected_tool"] == "propose_add_bundle"
    assert data["cart_proposal"]["product_ids"] == [
        "google-pixel-8",
        "unlimited-plus",
    ]
    assert data["cart_updated"] is False
    assert "phone budget" not in data["message"].lower()
    assert data["mode"] == "ai"


def test_ai_cannot_create_proposal_with_forged_product_id(client, monkeypatch):
    user_id, session_id = identity()

    async def forged_add(*_args, **_kwargs):
        return {
            "intent": "shopping",
            "goal": "cart_add",
            "scope": "retain",
            "product_ids": ["forged-free-phone"],
        }

    monkeypatch.setattr(shopassist, "_ai_parse", forged_add)
    response = chat(
        client,
        "Add the secret free phone to my cart",
        user_id,
        session_id,
    )
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "clarifying"
    assert data["cart_proposal"] is None
    assert session_store.get_cart_ids(session_id) == []


def test_ai_empty_remove_target_is_grounded_against_the_actual_cart(
    client,
    monkeypatch,
):
    user_id, session_id = identity()
    session_store.add_bundle_to_cart(
        session_id,
        ["google-pixel-8", "unlimited-plus"],
    )

    async def remove_without_id(*_args, **_kwargs):
        return {
            "intent": "shopping",
            "goal": "cart_remove",
            "scope": "retain",
            "product_ids": [],
        }

    monkeypatch.setattr(shopassist, "_ai_parse", remove_without_id)
    response = chat(
        client,
        "On second thought, take the plan back out of my basket",
        user_id,
        session_id,
    )
    data = response.json()

    assert response.status_code == 200
    assert data["selected_tool"] == "propose_remove_from_cart"
    assert data["cart_proposal"]["product_ids"] == ["unlimited-plus"]
    assert session_store.get_cart_ids(session_id) == [
        "google-pixel-8",
        "unlimited-plus",
    ]


def test_typoed_cart_lookup_overrides_bad_service_classification(
    client,
    monkeypatch,
):
    user_id, session_id = identity()
    session_store.add_bundle_to_cart(
        session_id,
        ["google-pixel-8", "unlimited-plus"],
    )

    async def misclassified_as_service(*_args, **_kwargs):
        return {
            "intent": "service",
            "goal": "converse",
            "scope": "retain",
        }

    monkeypatch.setattr(shopassist, "_ai_parse", misclassified_as_service)
    response = chat(
        client,
        "wjat is in my cart",
        user_id,
        session_id,
    )
    data = response.json()

    assert response.status_code == 200
    assert data["selected_tool"] == "cart_lookup"
    assert data["cart_summary"]["total_items"] == 2
    assert "Smart Cart suggests" not in data["message"]
    assert "Frag Magenta support" not in data["message"]


def test_empty_ai_add_ids_are_recovered_from_explicit_catalog_names(
    client,
    monkeypatch,
):
    user_id, session_id = identity()

    async def add_without_ids(*_args, **_kwargs):
        return {
            "intent": "shopping",
            "goal": "cart_add",
            "scope": "retain",
            "product_ids": [],
        }

    monkeypatch.setattr(shopassist, "_ai_parse", add_without_ids)
    response = chat(
        client,
        "Could you tuck the Pixel 8 and Unlimited Plus into my basket",
        user_id,
        session_id,
    )
    data = response.json()

    assert response.status_code == 200
    assert data["selected_tool"] == "propose_add_bundle"
    assert data["cart_proposal"]["product_ids"] == [
        "google-pixel-8",
        "unlimited-plus",
    ]


def test_pending_add_clarification_uses_the_next_named_product(
    client,
    monkeypatch,
):
    user_id, session_id = identity()
    calls = 0

    async def interpreted(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "intent": "shopping",
                "goal": "cart_add",
                "scope": "retain",
                "product_ids": [],
            }
        return {
            "intent": "shopping",
            "goal": "cart_lookup",
            "scope": "retain",
            "product_ids": [],
        }

    monkeypatch.setattr(shopassist, "_ai_parse", interpreted)
    clarification = chat(
        client,
        "Please add one of those",
        user_id,
        session_id,
    ).json()
    proposal_response = chat(
        client,
        "Pixel 8",
        user_id,
        session_id,
    ).json()

    assert clarification["status"] == "clarifying"
    assert proposal_response["selected_tool"] == "propose_add_to_cart"
    assert proposal_response["cart_proposal"]["product_ids"] == [
        "google-pixel-8",
    ]


def test_confirmation_is_idempotent_and_never_duplicates_mutation(client):
    user_id, session_id = identity()
    proposed = proposal(client, user_id, session_id)
    sid = proposed["session_id"]
    proposal_id = proposed["cart_proposal"]["proposal_id"]
    before_version = commerce_store.cart_version(sid)
    first = confirm(client, user_id, sid, proposal_id)
    same_key = confirm(client, user_id, sid, proposal_id)
    new_key = confirm(client, user_id, sid, proposal_id, "confirm-key-456")

    assert first.status_code == same_key.status_code == new_key.status_code == 200
    assert first.json()["added_product_ids"] == ["google-pixel-8"]
    assert same_key.json()["idempotent_replay"] is True
    assert new_key.json()["idempotent_replay"] is True
    assert commerce_store.cart_version(sid) == before_version + 1
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
    assert result.json()["detail"]["code"] == "price_changed"
    assert "pricing changed" in result.json()["detail"]["message"]
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
