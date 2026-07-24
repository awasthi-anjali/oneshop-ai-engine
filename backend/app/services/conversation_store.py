import uuid
from typing import Any


class ConversationStore:
    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    def get_or_create(self, session_id: str | None) -> tuple[str, list[dict[str, Any]]]:
        sid = session_id or str(uuid.uuid4())
        if sid not in self._sessions:
            self._sessions[sid] = []
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
