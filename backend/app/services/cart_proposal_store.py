"""Durable ShopAssist cart proposals and confirmation replay keys."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app.models.schemas import CartConfirmationResponse, CartProposal
from app.services.recommendation_db import get_recommendation_db


@dataclass
class CartProposalRecord:
    proposal: CartProposal
    session_id: str
    user_id: str | None
    created_at: float
    consumed: bool = False
    result: CartConfirmationResponse | None = None


class CartProposalStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path
        self._conn, self._lock = get_recommendation_db(db_path)
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cart_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    proposal_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_cart_proposals_session
                    ON cart_proposals(session_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS cart_confirmation_replay (
                    proposal_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY (proposal_id, idempotency_key)
                );
                """
            )

    def save(
        self,
        proposal_id: str,
        session_id: str,
        user_id: str | None,
        proposal: CartProposal,
    ) -> None:
        self._prune(max_rows=500)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO cart_proposals
                    (proposal_id, session_id, user_id, proposal_json, created_at, consumed, result_json)
                VALUES (?, ?, ?, ?, ?, 0, NULL)
                """,
                (
                    proposal_id,
                    session_id,
                    user_id,
                    proposal.model_dump_json(),
                    time.time(),
                ),
            )

    def get(self, proposal_id: str) -> CartProposalRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM cart_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        if not row:
            return None
        result = None
        if row["result_json"]:
            result = CartConfirmationResponse.model_validate_json(row["result_json"])
        return CartProposalRecord(
            proposal=CartProposal.model_validate_json(row["proposal_json"]),
            session_id=str(row["session_id"]),
            user_id=row["user_id"],
            created_at=float(row["created_at"]),
            consumed=bool(row["consumed"]),
            result=result,
        )

    def mark_consumed(self, proposal_id: str, result: CartConfirmationResponse) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE cart_proposals
                SET consumed = 1, result_json = ?
                WHERE proposal_id = ?
                """,
                (result.model_dump_json(), proposal_id),
            )

    def get_replay(self, proposal_id: str, idempotency_key: str) -> CartConfirmationResponse | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT result_json FROM cart_confirmation_replay
                WHERE proposal_id = ? AND idempotency_key = ?
                """,
                (proposal_id, idempotency_key),
            ).fetchone()
        if not row:
            return None
        return CartConfirmationResponse.model_validate_json(row["result_json"])

    def save_replay(
        self,
        proposal_id: str,
        idempotency_key: str,
        result: CartConfirmationResponse,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO cart_confirmation_replay
                    (proposal_id, idempotency_key, result_json)
                VALUES (?, ?, ?)
                """,
                (proposal_id, idempotency_key, result.model_dump_json()),
            )

    def _prune(self, max_rows: int = 500, max_age_seconds: float = 900) -> None:
        cutoff = time.time() - max_age_seconds
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM cart_proposals WHERE created_at < ?",
                (cutoff,),
            )
            count = self._conn.execute("SELECT COUNT(*) AS c FROM cart_proposals").fetchone()["c"]
            if count > max_rows:
                overflow = int(count) - max_rows
                stale_ids = self._conn.execute(
                    """
                    SELECT proposal_id FROM cart_proposals
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (overflow,),
                ).fetchall()
                for row in stale_ids:
                    pid = row["proposal_id"]
                    self._conn.execute(
                        "DELETE FROM cart_proposals WHERE proposal_id = ?",
                        (pid,),
                    )
                    self._conn.execute(
                        "DELETE FROM cart_confirmation_replay WHERE proposal_id = ?",
                        (pid,),
                    )


cart_proposal_store = CartProposalStore()
