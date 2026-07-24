from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings
from app.services.product_catalog import catalog


PriceSensitivity = Literal["unknown", "moderate", "high", "extreme"]
DecisionStyle = Literal["unknown", "balanced", "decisive", "researcher"]
NegotiationStyle = Literal["none", "discount_seeker", "waits_for_sale", "bundle_motivated"]
CommunicationStyle = Literal["neutral", "casual", "detailed", "concise", "friendly"]


def _bounded_text(value: str, limit: int = 96) -> str:
    return " ".join(value.strip().split())[:limit]


class BehavioralMemoryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_sensitivity: PriceSensitivity = "unknown"
    decision_style: DecisionStyle = "unknown"
    negotiation_style: NegotiationStyle = "none"
    communication_style: CommunicationStyle = "neutral"
    rejected_product_ids: list[str] = Field(default_factory=list, max_length=8)
    rejected_brands: list[str] = Field(default_factory=list, max_length=8)
    objections: list[str] = Field(default_factory=list, max_length=6)
    purchase_triggers: list[str] = Field(default_factory=list, max_length=6)
    trust_signals: list[str] = Field(default_factory=list, max_length=6)
    future_intent: str = Field(default="", max_length=120)
    updates_count: int = Field(default=0, ge=0)

    @field_validator(
        "rejected_product_ids",
        "rejected_brands",
        "objections",
        "purchase_triggers",
        "trust_signals",
    )
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_bounded_text(value) for value in values if _bounded_text(value)))

    @field_validator("future_intent")
    @classmethod
    def normalize_future_intent(cls, value: str) -> str:
        return _bounded_text(value, 120)


class BehavioralMemoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_sensitivity: PriceSensitivity | None = None
    decision_style: DecisionStyle | None = None
    negotiation_style: NegotiationStyle | None = None
    communication_style: CommunicationStyle | None = None
    rejected_product_ids: list[str] = Field(default_factory=list, max_length=8)
    rejected_brands: list[str] = Field(default_factory=list, max_length=8)
    objections: list[str] = Field(default_factory=list, max_length=6)
    purchase_triggers: list[str] = Field(default_factory=list, max_length=6)
    trust_signals: list[str] = Field(default_factory=list, max_length=6)
    future_intent: str | None = Field(default=None, max_length=120)

    @field_validator(
        "rejected_product_ids",
        "rejected_brands",
        "objections",
        "purchase_triggers",
        "trust_signals",
    )
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_bounded_text(value) for value in values if _bounded_text(value)))

    @field_validator("future_intent")
    @classmethod
    def normalize_future_intent(cls, value: str | None) -> str | None:
        return _bounded_text(value, 120) if value else None


class BehavioralMemoryRecord(BaseModel):
    user_id: str
    version: int = 0
    updated_at: str | None = None
    memory: BehavioralMemoryData = Field(default_factory=BehavioralMemoryData)


def merge_memory(
    current: BehavioralMemoryData,
    patch: BehavioralMemoryPatch,
    count_update: bool = True,
) -> BehavioralMemoryData:
    data = current.model_dump()
    patch_data = patch.model_dump(exclude_none=True)
    for field in (
        "price_sensitivity",
        "decision_style",
        "negotiation_style",
        "communication_style",
    ):
        value = patch_data.get(field)
        if value and value != "unknown":
            data[field] = value
    for field, limit in (
        ("rejected_product_ids", 8),
        ("rejected_brands", 8),
        ("objections", 6),
        ("purchase_triggers", 6),
        ("trust_signals", 6),
    ):
        incoming = patch_data.get(field, [])
        data[field] = list(dict.fromkeys([*incoming, *data.get(field, [])]))[:limit]
    if patch_data.get("future_intent"):
        data["future_intent"] = patch_data["future_intent"]
    data["updates_count"] = current.updates_count + (1 if count_update else 0)
    return BehavioralMemoryData(**data)


class BehavioralMemoryStore:
    """Durable structured memory. Raw chat text is never written to this store."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or settings.recommendation_db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS behavioral_memory (
                    user_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL DEFAULT 0,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS behavioral_memory_updates (
                    update_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_behavioral_memory_updates_user
                    ON behavioral_memory_updates(user_id, created_at DESC);
                """
            )

    def get(self, user_id: str) -> BehavioralMemoryRecord:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM behavioral_memory WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return BehavioralMemoryRecord(user_id=user_id)
        return BehavioralMemoryRecord(
            user_id=user_id,
            version=int(row["version"]),
            updated_at=str(row["updated_at"]),
            memory=BehavioralMemoryData(**json.loads(row["data_json"] or "{}")),
        )

    def apply_patch(
        self,
        user_id: str,
        update_id: str,
        patch: BehavioralMemoryPatch,
        count_update: bool = True,
    ) -> tuple[bool, BehavioralMemoryRecord]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            claimed = self._conn.execute(
                """
                INSERT OR IGNORE INTO behavioral_memory_updates
                    (update_id, user_id, created_at)
                VALUES (?, ?, ?)
                """,
                (update_id, user_id, now),
            ).rowcount == 1
            if not claimed:
                return False, self.get(user_id)
            current = self.get(user_id)
            merged = merge_memory(current.memory, patch, count_update=count_update)
            version = current.version + 1
            self._conn.execute(
                """
                INSERT INTO behavioral_memory (user_id, version, data_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    version = excluded.version,
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    version,
                    json.dumps(merged.model_dump(), sort_keys=True, separators=(",", ":")),
                    now,
                ),
            )
        return True, BehavioralMemoryRecord(
            user_id=user_id,
            version=version,
            updated_at=now,
            memory=merged,
        )

    def reset(self, user_id: str) -> bool:
        with self._lock, self._conn:
            deleted = self._conn.execute(
                "DELETE FROM behavioral_memory WHERE user_id = ?", (user_id,)
            ).rowcount > 0
            self._conn.execute(
                "DELETE FROM behavioral_memory_updates WHERE user_id = ?", (user_id,)
            )
        return deleted

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def bounded_memory_context(
    user_id: str | None,
    store: BehavioralMemoryStore | None = None,
) -> dict:
    if not user_id:
        return {}
    record = (store or behavioral_memory_store).get(user_id)
    memory = record.memory
    context = {
        "version": record.version,
        "price_sensitivity": memory.price_sensitivity,
        "decision_style": memory.decision_style,
        "negotiation_style": memory.negotiation_style,
        "communication_style": memory.communication_style,
        "rejected_product_ids": memory.rejected_product_ids,
        "rejected_brands": memory.rejected_brands,
        "objections": memory.objections[:3],
        "purchase_triggers": memory.purchase_triggers[:3],
        "trust_signals": memory.trust_signals[:3],
        "future_intent": memory.future_intent,
    }
    return {
        key: value
        for key, value in context.items()
        if value not in ("", "unknown", "none", "neutral", [], 0)
    }


def _explicit_rejections(text: str) -> tuple[list[str], list[str]]:
    lowered = text.lower()
    rejection_phrases = (
        "don't like",
        "do not like",
        "avoid",
        "not interested in",
        "never suggest",
        "hate",
    )
    rejection_clauses: list[str] = []
    for phrase in rejection_phrases:
        for match in re.finditer(re.escape(phrase), lowered):
            tail = lowered[match.start():match.start() + 120]
            rejection_clauses.append(re.split(r"[.;!?]|\bbut\b|\bhowever\b", tail, maxsplit=1)[0])
    if not rejection_clauses:
        return [], []
    product_ids = [
        product.id
        for product in catalog.all
        if any(
            product.name.lower() in clause
            or product.id.replace("-", " ") in clause
            for clause in rejection_clauses
        )
    ]
    brands = [
        brand
        for brand in sorted({product.brand for product in catalog.all})
        if any(
            re.search(rf"\b{re.escape(brand.lower())}\b", clause)
            for clause in rejection_clauses
        )
    ]
    return product_ids[:8], brands[:8]


def deterministic_memory_patch(
    turns: list[dict[str, str]],
    future_intent: str = "",
) -> BehavioralMemoryPatch:
    user_messages = [
        _bounded_text(turn.get("content", ""), 300)
        for turn in turns
        if turn.get("role") == "user"
    ]
    text = " ".join(user_messages).lower()
    rejected_products, rejected_brands = _explicit_rejections(text)

    price_sensitivity: PriceSensitivity | None = None
    if any(phrase in text for phrase in ("too expensive", "cheaper", "lowest price", "strict budget")):
        price_sensitivity = "high"
    if any(phrase in text for phrase in ("as cheap as possible", "absolute cheapest")):
        price_sensitivity = "extreme"

    decision_style: DecisionStyle | None = None
    if any(word in text for word in ("compare", "specs", "differences", "research", "review")):
        decision_style = "researcher"
    elif any(phrase in text for phrase in ("just tell me", "pick one", "best one")):
        decision_style = "decisive"

    negotiation_style: NegotiationStyle | None = None
    if any(word in text for word in ("discount", "deal", "coupon")):
        negotiation_style = "discount_seeker"
    elif "wait for" in text and "sale" in text:
        negotiation_style = "waits_for_sale"
    elif "bundle" in text:
        negotiation_style = "bundle_motivated"

    communication_style: CommunicationStyle | None = None
    if "just tell me" in text or "keep it short" in text:
        communication_style = "concise"
    elif any(word in text for word in ("specs", "details", "explain", "compare")):
        communication_style = "detailed"
    elif any(word in text for word in ("hey", "cool", "thanks", "please")):
        communication_style = "friendly"

    objections: list[str] = []
    for phrase, label in (
        ("battery", "battery life"),
        ("don't trust", "brand trust"),
        ("too expensive", "price"),
        ("worried", "product concern"),
        ("won't last", "durability"),
    ):
        if phrase in text:
            objections.append(label)

    triggers = [
        label
        for phrase, label in (
            ("gym", "gym use"),
            ("gift", "gifting"),
            ("photography", "photography"),
            ("camera", "photography"),
            ("travel", "travel"),
            ("work", "work"),
            ("gaming", "gaming"),
            ("family", "family"),
        )
        if phrase in text
    ]
    trust_signals = [
        label
        for phrase, label in (
            ("friend", "friend recommendation"),
            ("youtube", "video reviews"),
            ("review", "reviews"),
            ("rating", "ratings"),
            ("always used", "brand loyalty"),
        )
        if phrase in text
    ]
    return BehavioralMemoryPatch(
        price_sensitivity=price_sensitivity,
        decision_style=decision_style,
        negotiation_style=negotiation_style,
        communication_style=communication_style,
        rejected_product_ids=rejected_products,
        rejected_brands=rejected_brands,
        objections=list(dict.fromkeys(objections)),
        purchase_triggers=list(dict.fromkeys(triggers)),
        trust_signals=list(dict.fromkeys(trust_signals)),
        future_intent=future_intent or None,
    )


behavioral_memory_store = BehavioralMemoryStore()
