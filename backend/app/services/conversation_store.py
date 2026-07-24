import uuid
from typing import Any

SYSTEM_PROMPT = """You are ShopAssist, an intelligent conversational shopping assistant for OneShop (web) and OneApp (mobile) — a digital commerce platform selling phones, tablets, plans, accessories, and devices.

Your role:
- Help customers discover products that match their needs using natural language
- Compare products side-by-side when asked
- Guide customers toward the best purchase decision
- Be friendly, concise, and helpful

When you need product data, use the provided tools. Always ground recommendations in actual catalog data.
For comparisons, highlight key differences in price, features, and specs with clear pros/cons.
If customer context is provided (wishlist, cart, viewed products), reference it naturally.
If a customer is unsure, ask one clarifying question rather than overwhelming them.

Available product categories: phones, tablets, plans, accessories, devices.
Currency is USD. Plans are monthly pricing.

Respond in plain conversational text. Product cards will be shown separately in the UI when you reference specific products by ID."""


class ConversationStore:
    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    def get_or_create(self, session_id: str | None) -> tuple[str, list[dict[str, Any]]]:
        sid = session_id or str(uuid.uuid4())
        if sid not in self._sessions:
            self._sessions[sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
        return sid, self._sessions[sid]

    def get_history_snippets(self, session_id: str, limit: int = 6) -> list[str]:
        history = self._sessions.get(session_id, [])
        return [
            m["content"] for m in history
            if m.get("role") in ("user", "assistant")
        ][-limit:]

    def append(self, session_id: str, message: dict[str, Any]) -> None:
        self._sessions.setdefault(session_id, []).append(message)


conversation_store = ConversationStore()
