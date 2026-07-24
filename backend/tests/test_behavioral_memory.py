import asyncio
import json
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import ChatRequest
from app.services.behavioral_memory import (
    BehavioralMemoryPatch,
    BehavioralMemoryStore,
    behavioral_memory_store,
    bounded_memory_context,
    deterministic_memory_patch,
)
from app.services.shopassist_service import ShopAssistService


def test_store_is_durable_idempotent_bounded_and_isolated(tmp_path):
    db_path = tmp_path / "memory.db"
    store = BehavioralMemoryStore(db_path)
    patch = BehavioralMemoryPatch(
        price_sensitivity="high",
        decision_style="researcher",
        rejected_brands=["Apple"],
        objections=["price"],
        future_intent="phone, photography",
    )

    accepted, first = store.apply_patch("user_a", "dream:user_a:s1:5", patch)
    duplicate, repeated = store.apply_patch("user_a", "dream:user_a:s1:5", patch)
    assert accepted is True
    assert duplicate is False
    assert first.version == repeated.version == 1
    assert store.get("user_b").version == 0
    store.close()

    reopened = BehavioralMemoryStore(db_path)
    assert reopened.get("user_a").memory.rejected_brands == ["Apple"]
    assert bounded_memory_context("user_a", reopened)["decision_style"] == "researcher"
    assert bounded_memory_context("user_b", reopened) == {}
    reopened.close()


def test_store_schema_and_rows_never_persist_raw_chat(tmp_path):
    db_path = tmp_path / "memory.db"
    store = BehavioralMemoryStore(db_path)
    secret = "alice.private@example.com"
    store.apply_patch(
        "user_a",
        "dream:user_a:s1:5",
        BehavioralMemoryPatch(objections=["price"], future_intent="phone"),
    )
    store.close()

    connection = sqlite3.connect(db_path)
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(behavioral_memory)").fetchall()
    }
    rows = json.dumps(
        connection.execute("SELECT * FROM behavioral_memory").fetchall()
    )
    connection.close()
    assert columns == {"user_id", "version", "data_json", "updated_at"}
    assert secret not in rows
    assert "recent_conversation" not in rows


def test_memory_api_is_allow_listed_and_resettable():
    user_id = "memory_api_test_user"
    behavioral_memory_store.reset(user_id)
    behavioral_memory_store.apply_patch(
        user_id,
        "api-test",
        BehavioralMemoryPatch(decision_style="decisive", objections=["price"]),
    )
    client = TestClient(app)

    response = client.get(f"/api/recommendations/{user_id}/memory")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 1
    assert payload["assistant_context"]["decision_style"] == "decisive"
    assert set(payload["memory"]) == {
        "price_sensitivity",
        "decision_style",
        "negotiation_style",
        "communication_style",
        "rejected_product_ids",
        "rejected_brands",
        "objections",
        "purchase_triggers",
        "trust_signals",
        "future_intent",
        "updates_count",
    }
    reset = client.delete(f"/api/recommendations/{user_id}/memory")
    assert reset.status_code == 200
    assert reset.json()["deleted"] is True
    assert client.get(f"/api/recommendations/{user_id}/memory").json()["version"] == 0


def test_deterministic_extraction_requires_explicit_evidence():
    patch = deterministic_memory_patch(
        [
            {
                "role": "user",
                "content": (
                    "Compare the specs. Apple is too expensive and I don't like Apple. "
                    "Samsung is fine. Any discount for a camera phone for travel?"
                ),
            }
        ],
        "phone, photography, travel",
    )
    assert patch.price_sensitivity == "high"
    assert patch.decision_style == "researcher"
    assert patch.negotiation_style == "discount_seeker"
    assert patch.communication_style == "detailed"
    assert patch.rejected_brands == ["Apple"]
    assert "Samsung" not in patch.rejected_brands
    assert patch.purchase_triggers == ["photography", "travel"]

    silence = deterministic_memory_patch(
        [{"role": "user", "content": "Recommend a phone"}]
    )
    assert silence.price_sensitivity is None
    assert silence.rejected_brands == []


def test_dreaming_update_runs_at_five_turn_boundary(tmp_path):
    store = BehavioralMemoryStore(tmp_path / "memory.db")
    service = ShopAssistService(memory_store=store)
    service._client = None

    async def run():
        messages = [
            "Recommend an Android camera phone under $800",
            "Compare the phone specs and details",
            "Apple is too expensive; I don't like Apple phones",
            "Is there any phone discount or deal?",
            "Just tell me the best phone for travel",
        ]
        for message in messages:
            await service.chat(
                ChatRequest(
                    message=message,
                    user_id="memory_user",
                    session_id="memory-session",
                )
            )
        await service.wait_for_memory_updates()

    asyncio.run(run())
    record = store.get("memory_user")
    assert record.version == 1
    assert record.memory.updates_count == 1
    assert record.memory.price_sensitivity == "high"
    assert record.memory.decision_style == "researcher"
    assert record.memory.communication_style == "concise"
    assert record.memory.rejected_brands == ["Apple"]
    assert "photography" in record.memory.purchase_triggers
    assert record.memory.future_intent
    store.close()


def test_memory_rejection_is_soft_unless_current_request_is_explicit(tmp_path):
    store = BehavioralMemoryStore(tmp_path / "memory.db")
    store.apply_patch(
        "memory_user",
        "seed",
        BehavioralMemoryPatch(rejected_brands=["Samsung"]),
    )
    service = ShopAssistService(memory_store=store)
    service._client = None

    async def run():
        general = await service.chat(
            ChatRequest(
                message="Recommend an Android phone under $800",
                user_id="memory_user",
                session_id="general",
            )
        )
        explicit = await service.chat(
            ChatRequest(
                message="Recommend a Samsung Android phone under $500",
                user_id="memory_user",
                session_id="explicit",
            )
        )
        return general, explicit

    general, explicit = asyncio.run(run())
    assert all(rec.product.brand != "Samsung" for rec in general.recommendations)
    assert explicit.recommendations[0].product.id == "samsung-a54"
    store.close()


def test_last_time_reference_uses_structured_memory_and_current_constraints_win(tmp_path):
    store = BehavioralMemoryStore(tmp_path / "memory.db")
    store.apply_patch(
        "reference_user",
        "seed",
        BehavioralMemoryPatch(
            future_intent="phone, photography, android, device budget under $800"
        ),
    )
    service = ShopAssistService(memory_store=store)
    service._client = None

    async def run():
        recalled = await service.chat(
            ChatRequest(
                message="Show me something like last time",
                user_id="reference_user",
                session_id="recalled",
            )
        )
        overridden = await service.chat(
            ChatRequest(
                message="Show me an iPhone like last time under $500",
                user_id="reference_user",
                session_id="overridden",
            )
        )
        return recalled, overridden

    recalled, overridden = asyncio.run(run())
    assert recalled.status.value == "recommended"
    assert recalled.need_profile.platform == "android"
    assert recalled.need_profile.use_cases == ["photography"]
    assert all(rec.product.price <= 800 for rec in recalled.recommendations)
    assert overridden.need_profile.platform == "ios"
    assert overridden.need_profile.device_budget_max == 500
    assert overridden.recommendations[0].product.id == "iphone-se"
    store.close()


def test_memory_changes_presentation_not_validated_products(tmp_path):
    store = BehavioralMemoryStore(tmp_path / "memory.db")
    store.apply_patch(
        "concise_user",
        "seed",
        BehavioralMemoryPatch(
            price_sensitivity="high",
            decision_style="decisive",
            communication_style="concise",
        ),
    )
    service = ShopAssistService(memory_store=store)
    service._client = None

    async def run():
        plain = await service.chat(
            ChatRequest(
                message="Recommend an Android phone under $800",
                user_id="plain_user",
                session_id="plain",
            )
        )
        adapted = await service.chat(
            ChatRequest(
                message="Recommend an Android phone under $800",
                user_id="concise_user",
                session_id="adapted",
            )
        )
        return plain, adapted

    plain, adapted = asyncio.run(run())
    assert [rec.product.id for rec in plain.recommendations] == [
        rec.product.id for rec in adapted.recommendations
    ]
    assert adapted.message.startswith("Best match:")
    assert not any(action.type.value == "COMPARE" for action in adapted.actions)
    store.close()


def test_explicit_current_turn_style_overrides_durable_researcher_memory(tmp_path):
    store = BehavioralMemoryStore(tmp_path / "memory.db")
    store.apply_patch(
        "researcher_user",
        "seed",
        BehavioralMemoryPatch(
            price_sensitivity="high",
            decision_style="researcher",
            communication_style="detailed",
        ),
    )
    service = ShopAssistService(memory_store=store)
    service._client = None

    response = asyncio.run(
        service.chat(
            ChatRequest(
                message="Just tell me the best Android phone under $800 for travel",
                user_id="researcher_user",
                session_id="current-turn-wins",
            )
        )
    )

    assert response.message.startswith("Best match:")
    assert "compare" not in response.message.lower()
    assert not any(action.type.value == "COMPARE" for action in response.actions)
    assert len(response.recommendations) == 2
    assert store.get("researcher_user").memory.decision_style == "researcher"
    assert store.get("researcher_user").memory.communication_style == "detailed"
    store.close()


def test_dreaming_model_cannot_create_hard_exclusions_without_explicit_evidence(tmp_path):
    service = ShopAssistService(
        memory_store=BehavioralMemoryStore(tmp_path / "memory.db")
    )
    model_patch = BehavioralMemoryPatch(
        rejected_product_ids=["google-pixel-8"],
        rejected_brands=["Google"],
        objections=["battery life"],
        future_intent="phone, device budget under $1",
    )
    evidence_patch = deterministic_memory_patch(
        [{"role": "user", "content": "Recommend a camera phone"}]
    )
    merged = service._merge_memory_patches(model_patch, evidence_patch)
    assert merged.rejected_product_ids == []
    assert merged.rejected_brands == []
    assert merged.future_intent is None
    service._memory_store.close()


def test_system_prompt_receives_bounded_memory_and_rejects_invented_composition(tmp_path):
    store = BehavioralMemoryStore(tmp_path / "memory.db")
    store.apply_patch(
        "prompt_user",
        "seed",
        BehavioralMemoryPatch(
            price_sensitivity="high",
            decision_style="researcher",
            objections=["price"],
        ),
    )

    class QueuedCompletions:
        def __init__(self):
            self.calls = []
            self.outputs = [
                '{"intent":"shopping","need_patch":{"categories":["phone"],'
                '"platform":"android","device_budget_max":800}}',
                '{"message":"Google Pixel 8 is guaranteed with a discount for $1."}',
            ]

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=self.outputs.pop(0))
                    )
                ]
            )

    completions = QueuedCompletions()
    service = ShopAssistService(memory_store=store)
    service._client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    response = asyncio.run(
        service.chat(
            ChatRequest(
                message="Recommend an Android phone under $800",
                user_id="prompt_user",
                session_id="prompt-session",
            )
        )
    )

    parser_context = completions.calls[0]["messages"][1]["content"]
    composer_context = json.loads(completions.calls[1]["messages"][1]["content"])
    assert "soft context only" in parser_context
    assert '"decision_style": "researcher"' in parser_context
    assert (
        composer_context["trusted_context"]["behavioral_memory"]["objections"]
        == ["price"]
    )
    assert "guaranteed" not in response.message
    assert "discount" not in response.message
    assert "$1" not in response.message
    assert response.recommendations[0].product.price <= 800
    store.close()


def test_memory_sanitizer_removes_pii_and_bounds_input(tmp_path):
    service = ShopAssistService(
        memory_store=BehavioralMemoryStore(tmp_path / "memory.db")
    )
    text = (
        "Email alice.private@example.com or call +1 (212) 555-0100. "
        + ("x" * 500)
    )
    sanitized = service._sanitize_memory_text(text)
    assert "alice.private@example.com" not in sanitized
    assert "555-0100" not in sanitized
    assert "[email removed]" in sanitized
    assert "[phone removed]" in sanitized
    assert len(sanitized) <= 300
    service._memory_store.close()
