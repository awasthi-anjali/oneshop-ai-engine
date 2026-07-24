from __future__ import annotations

import json
import sqlite3
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import RecommendationInteractionRequest
from app.services.product_catalog import catalog


EVENT_WEIGHTS = {
    "impression": 0.0,
    "rec_click": 2.0,
    "product_view": 1.0,
    "wishlist_add": 3.0,
    "wishlist_remove": -1.0,
    "cart_add": 4.0,
    "cart_remove": -0.5,
    "dismiss": -1.0,
}


DEMO_PROFILES = [
    {"user_id": "user_001", "name": "Alex", "label": "Budget Student", "emoji": "🎓"},
    {"user_id": "user_011", "name": "Dev", "label": "Tech Enthusiast", "emoji": "🚀"},
    {"user_id": "user_021", "name": "Morgan", "label": "Business Pro", "emoji": "💼"},
    {"user_id": "user_031", "name": "Greta", "label": "Senior", "emoji": "👵"},
    {"user_id": "user_041", "name": "Chris", "label": "Family Parent", "emoji": "👨‍👩‍👧"},
]


DEMO_INTERACTIONS = {
    "user_001": ["iphone-se", "samsung-a54", "unlimited-essential", "data-only-plan"],
    "user_011": ["samsung-s24-ultra", "oneplus-12", "google-pixel-8", "galaxy-tab-s9"],
    "user_021": ["iphone-15-pro", "ipad-air", "airpods-pro", "magsafe-charger"],
    "user_031": ["iphone-se", "magsafe-charger", "phone-case-universal", "unlimited-essential"],
    "user_041": ["family-plan", "samsung-a54", "galaxy-tab-s9", "galaxy-buds2-pro"],
}


class InteractionStore:
    """Small durable event log. SessionStore remains authoritative for cart/wishlist state."""

    def __init__(self, db_path: str | Path | None = None, seed_demo: bool = True) -> None:
        self.db_path = str(db_path or settings.recommendation_db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()
        if seed_demo:
            self.seed_demo_profiles()

    def _initialize(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    event_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    product_id TEXT,
                    channel TEXT NOT NULL,
                    session_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_interactions_user_created
                    ON interactions(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS profile_versions (
                    user_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def seed_demo_profiles(self) -> None:
        for user_id, product_ids in DEMO_INTERACTIONS.items():
            for index, product_id in enumerate(product_ids):
                request = RecommendationInteractionRequest(
                    event_id=f"seed:{user_id}:{index}",
                    user_id=user_id,
                    event_type="product_view" if index % 2 else "rec_click",
                    product_id=product_id,
                    channel="oneapp" if index == len(product_ids) - 1 else "oneshop",
                    metadata={"surface": "demo_seed"},
                )
                self.append(request)

    def append(self, event: RecommendationInteractionRequest) -> tuple[bool, int]:
        metadata_json = json.dumps(
            event.metadata.model_dump(exclude_none=True), sort_keys=True, separators=(",", ":")
        )
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO interactions
                    (event_id, user_id, event_type, product_id, channel, session_id, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.user_id,
                    event.event_type.value,
                    event.product_id,
                    event.channel.value,
                    event.session_id,
                    metadata_json,
                    now,
                ),
            )
            accepted = cursor.rowcount == 1
            if accepted:
                self._conn.execute(
                    """
                    INSERT INTO profile_versions(user_id, version) VALUES (?, 1)
                    ON CONFLICT(user_id) DO UPDATE SET version = version + 1
                    """,
                    (event.user_id,),
                )
            version = self.version(event.user_id)
        return accepted, version

    def version(self, user_id: str) -> int:
        row = self._conn.execute(
            "SELECT version FROM profile_versions WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row["version"]) if row else 0

    def events(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM interactions WHERE user_id = ? ORDER BY created_at DESC, event_id DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def profile(self, user_id: str) -> dict[str, Any]:
        brand_scores: defaultdict[str, float] = defaultdict(float)
        category_scores: defaultdict[str, float] = defaultdict(float)
        prices: list[tuple[float, float]] = []
        recent_views: list[str] = []
        channels: set[str] = set()
        counts: Counter[str] = Counter()
        last_query = ""

        rows = self.events(user_id)
        for row in rows:
            event_type = str(row["event_type"])
            counts[event_type] += 1
            channels.add(str(row["channel"]))
            metadata = json.loads(row["metadata_json"] or "{}")
            if not last_query and metadata.get("query"):
                last_query = metadata["query"]
            product = catalog.get_by_id(row["product_id"]) if row["product_id"] else None
            if not product:
                continue
            if event_type in {"product_view", "rec_click"} and product.id not in recent_views:
                recent_views.append(product.id)
            weight = EVENT_WEIGHTS.get(event_type, 0.0)
            if weight > 0:
                brand_scores[product.brand] += weight
                category_scores[product.category.value] += weight
                prices.append((product.price, weight))

        def normalize(values: dict[str, float]) -> dict[str, float]:
            total = sum(max(0.0, value) for value in values.values())
            if total <= 0:
                return {}
            return {
                key: round(max(0.0, value) / total, 4)
                for key, value in sorted(values.items())
                if value > 0
            }

        weighted_total = sum(weight for _, weight in prices)
        centroid = sum(price * weight for price, weight in prices) / weighted_total if weighted_total else 0.0
        max_catalog_price = max((p.price for p in catalog.all), default=1.0)
        return {
            "user_id": user_id,
            "brand_affinity": normalize(brand_scores),
            "category_affinity": normalize(category_scores),
            "price_signal": {
                "centroid": round(centroid, 2),
                "min": round(min((price for price, _ in prices), default=0.0), 2),
                "max": round(max((price for price, _ in prices), default=0.0), 2),
                "normalized": round(min(1.0, max(0.0, centroid / max_catalog_price)), 4),
            },
            "recent_views": recent_views[:10],
            "channels": sorted(channels),
            "interaction_counts": dict(sorted(counts.items())),
            "total_interactions": sum(counts.values()),
            "last_query": last_query,
            "cold_start": not bool(prices),
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


interaction_store = InteractionStore()
