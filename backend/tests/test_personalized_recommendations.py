import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import RecommendationInteractionRequest
from app.services.checkout_profile_store import reset_checkout_profile_overrides
from app.services.interaction_store import InteractionStore
from app.services.product_catalog import catalog


@pytest.fixture(autouse=True)
def _isolated_checkout_profiles():
    reset_checkout_profile_overrides()
    yield
    reset_checkout_profile_overrides()


def _client() -> TestClient:
    return TestClient(app)


def _event(user_id: str, event_type: str, product_id: str | None = None, **extra) -> dict:
    return {
        "event_id": f"test:{uuid.uuid4()}",
        "user_id": user_id,
        "event_type": event_type,
        "product_id": product_id,
        "channel": "oneshop",
        **extra,
    }


def test_checkout_profile_api_and_chat_update():
    client = _client()
    profile = client.get("/api/recommendations/user_001/checkout-profile").json()
    assert profile["full_name"] == "Anjali"
    assert profile["email"] == "anjali00223@gmail.com"

    updated = client.patch(
        "/api/recommendations/user_001/checkout-profile",
        json={"email": "alex.new@studentmail.demo"},
    ).json()
    assert updated["email"] == "alex.new@studentmail.demo"
    assert updated["full_name"] == "Anjali"

    chat = client.post(
        "/api/chat",
        json={
            "message": "Change my card to 4242 4242 4242 9999",
            "channel": "oneshop",
            "user_id": "user_001",
        },
    ).json()
    assert chat["checkout_profile"]["card_number"].endswith("9999")


def test_demo_profiles_are_actual_catalog_personas_with_divergent_rankings():
    client = _client()
    profiles = client.get("/api/recommendations/demo-profiles").json()["profiles"]
    assert [profile["user_id"] for profile in profiles] == [
        "user_001", "user_011", "user_021", "user_031", "user_041"
    ]
    assert profiles[0]["full_name"] == "Anjali"
    assert profiles[0]["email"] == "anjali00223@gmail.com"
    assert profiles[0]["card_number"].endswith("4242")

    rankings = {}
    for profile in profiles:
        response = client.get(
            f"/api/recommendations/{profile['user_id']}",
            params={"query": "phone", "limit": 6},
        )
        assert response.status_code == 200
        data = response.json()
        rankings[profile["user_id"]] = [item["product"]["id"] for item in data["recommendations"]]
        assert all(catalog.get_by_id(product_id) for product_id in rankings[profile["user_id"]])
    assert rankings["user_001"][:3] != rankings["user_011"][:3]
    assert rankings["user_011"][:3] != rankings["user_021"][:3]


def test_sqlite_event_log_is_persistent_and_event_id_is_idempotent(tmp_path):
    path = tmp_path / "events.sqlite3"
    first = InteractionStore(path, seed_demo=False)
    event = RecommendationInteractionRequest(
        event_id="stable-event-001",
        user_id="persist_user",
        event_type="rec_click",
        product_id="google-pixel-8",
        channel="oneshop",
    )
    assert first.append(event) == (True, 1)
    assert first.append(event) == (False, 1)
    first.close()

    second = InteractionStore(path, seed_demo=False)
    assert second.version("persist_user") == 1
    assert len(second.events("persist_user")) == 1
    assert second.profile("persist_user")["brand_affinity"] == {"Google": 1.0}
    second.close()


def test_tracking_endpoint_rejects_unknown_products_and_unrestricted_metadata():
    client = _client()
    unknown = client.post(
        "/api/recommendations/interactions",
        json=_event("validation_user", "product_view", "not-in-catalog"),
    )
    assert unknown.status_code == 404

    raw_chat = _event("validation_user", "product_view", "iphone-se")
    raw_chat["metadata"] = {"raw_chat": "my email is user@example.test"}
    response = client.post("/api/recommendations/interactions", json=raw_chat)
    assert response.status_code == 422


def test_impression_is_neutral_but_click_updates_profile_and_version():
    client = _client()
    user = f"neutral_{uuid.uuid4().hex}"
    before = client.get(f"/api/recommendations/{user}").json()
    impression = _event(
        user, "impression", "iphone-15-pro", metadata={"surface": "for_you", "visible": True}
    )
    tracked = client.post("/api/recommendations/interactions", json=impression).json()
    after_impression = client.get(f"/api/recommendations/{user}").json()
    assert tracked["accepted"] is True
    assert after_impression["version"] == before["version"] + 1
    assert after_impression["profile"]["brand_affinity"] == {}
    assert after_impression["profile"]["price_signal"]["centroid"] == 0

    clicked = client.post(
        "/api/recommendations/interactions",
        json=_event(user, "rec_click", "iphone-15-pro", metadata={"rec_position": 0}),
    ).json()
    after_click = client.get(f"/api/recommendations/{user}").json()
    assert clicked["version"] == after_impression["version"] + 1
    assert after_click["profile"]["brand_affinity"] == {"Apple": 1.0}


def test_versioned_update_path_is_changed_only_after_new_event():
    client = _client()
    user = f"updates_{uuid.uuid4().hex}"
    initial = client.get(f"/api/recommendations/{user}").json()
    unchanged = client.get(
        f"/api/recommendations/{user}/updates",
        params={"after_version": initial["version"], "session_id": initial["session_id"]},
    ).json()
    assert unchanged["changed"] is False
    assert unchanged["recommendations"] == []

    client.post(
        "/api/recommendations/interactions",
        json=_event(
            user,
            "product_view",
            "oneplus-12",
            session_id=initial["session_id"],
            channel="oneapp",
        ),
    )
    changed = client.get(
        f"/api/recommendations/{user}/updates",
        params={"after_version": initial["version"], "channel": "oneapp"},
    ).json()
    assert changed["changed"] is True
    assert changed["version"] > initial["version"]
    assert changed["recommendations"]


def test_same_profile_continues_across_channels_without_cross_user_leakage():
    client = _client()
    first_user = f"continuity_a_{uuid.uuid4().hex}"
    second_user = f"continuity_b_{uuid.uuid4().hex}"
    web = client.get(
        f"/api/recommendations/{first_user}",
        params={"session_id": "shared-browser-session", "channel": "oneshop"},
    ).json()
    app_response = client.get(
        f"/api/recommendations/{first_user}",
        params={"channel": "oneapp"},
    ).json()
    assert app_response["session_id"] == web["session_id"]
    assert set(app_response["profile"]["channels"]) == {"oneshop", "oneapp"}

    isolated = client.get(
        f"/api/recommendations/{second_user}",
        params={"session_id": web["session_id"], "channel": "oneshop"},
    ).json()
    assert isolated["session_id"] != web["session_id"]
    assert isolated["profile"]["total_interactions"] == 0


def test_intelligence_profile_uses_the_same_isolated_cart_as_shopassist():
    client = _client()
    first_user = f"intelligence_a_{uuid.uuid4().hex}"
    second_user = f"intelligence_b_{uuid.uuid4().hex}"

    first = client.get(
        "/api/intelligence/profile",
        params={"user_id": first_user, "channel": "oneshop"},
    ).json()
    client.post(
        "/api/customer/cart/add",
        json={
            "session_id": first["session_id"],
            "product_id": "google-pixel-8",
            "channel": "oneshop",
        },
    )
    first_again = client.get(
        "/api/intelligence/profile",
        params={
            "session_id": first["session_id"],
            "user_id": first_user,
            "channel": "oneshop",
        },
    ).json()
    isolated = client.get(
        "/api/intelligence/profile",
        params={
            "session_id": first["session_id"],
            "user_id": second_user,
            "channel": "oneshop",
        },
    ).json()

    assert [item["id"] for item in first_again["cart"]] == ["google-pixel-8"]
    assert isolated["session_id"] != first_again["session_id"]
    assert isolated["cart"] == []


def test_session_cart_and_wishlist_are_authoritative_exclusions():
    client = _client()
    user = f"exclusions_{uuid.uuid4().hex}"
    initial = client.get(f"/api/recommendations/{user}").json()
    sid = initial["session_id"]
    client.post(
        "/api/customer/cart/add",
        json={"session_id": sid, "product_id": "iphone-15-pro", "channel": "oneshop"},
    )
    client.post(
        "/api/customer/wishlist/toggle",
        json={"session_id": sid, "product_id": "google-pixel-8", "channel": "oneshop"},
    )
    payload = client.get(
        f"/api/recommendations/{user}", params={"session_id": sid, "limit": 12}
    ).json()
    ids = {item["product"]["id"] for item in payload["recommendations"]}
    assert "iphone-15-pro" not in ids
    assert "google-pixel-8" not in ids
    assert payload["profile"]["cart_exclusions"] == ["iphone-15-pro"]
    assert payload["profile"]["wishlist_exclusions"] == ["google-pixel-8"]

    # A tracked analytics event alone never becomes competing cart truth.
    other = f"analytics_cart_{uuid.uuid4().hex}"
    client.post(
        "/api/recommendations/interactions",
        json=_event(other, "cart_add", "iphone-se"),
    )
    analytics_only = client.get(
        f"/api/recommendations/{other}", params={"limit": 12}
    ).json()
    assert "iphone-se" not in analytics_only["profile"]["cart_exclusions"]


def test_scores_are_normalized_diverse_deterministic_and_explanations_are_grounded():
    client = _client()
    params = {"query": "android camera phone", "limit": 8}
    first = client.get("/api/recommendations/user_011", params=params).json()
    second = client.get(
        "/api/recommendations/user_011",
        params={**params, "session_id": first["session_id"]},
    ).json()
    assert first["recommendations"] == second["recommendations"]

    brands = [item["product"]["brand"] for item in first["recommendations"]]
    assert max(brands.count(brand) for brand in set(brands)) <= 2
    valid_codes = {
        "POPULAR_COLD_START", "PREFERRED_BRAND", "PREFERRED_CATEGORY",
        "PRICE_SIGNAL_MATCH", "QUERY_MATCH", "RECENTLY_VIEWED", "CATALOG_POPULARITY",
    }
    for item in first["recommendations"]:
        assert 0 <= item["score"] <= 1
        assert set(item["score_breakdown"]) == {
            "semantic", "brand_affinity", "category_affinity",
            "price_fit", "popularity", "recency",
        }
        assert all(0 <= value <= 1 for value in item["score_breakdown"].values())
        assert set(item["reason_codes"]) <= valid_codes
        assert item["product"]["brand"] in item["explanation"] or any(
            phrase in item["explanation"]
            for phrase in ("catalog price", "normalized query", "recently viewed", "catalog rating")
        )


def test_cold_start_uses_catalog_popularity_and_shopassist_keeps_hard_constraints():
    client = _client()
    user = f"cold_{uuid.uuid4().hex}"
    cold = client.get(f"/api/recommendations/{user}", params={"limit": 4}).json()
    assert cold["profile"]["cold_start"] is True
    assert cold["retrieval_method"] == "popularity"
    assert all("POPULAR_COLD_START" in item["reason_codes"] for item in cold["recommendations"])

    response = client.post(
        "/api/chat",
        json={
            "message": "Recommend an Android phone under $500",
            "channel": "oneshop",
            "user_id": "user_021",
            "personalization_context": {
                "preferred_brands": ["Apple"],
                "preferred_categories": ["phone"],
                "price_centroid": 999,
                "interaction_count": 999,
            },
        },
    )
    assert response.status_code == 200
    products = [item["product"] for item in response.json()["recommendations"]]
    assert products
    assert all(product["price"] <= 500 for product in products)
    assert all("android" in product["tags"] for product in products)
