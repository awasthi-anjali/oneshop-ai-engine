"""Shared SQLite connection per database path (avoids lock contention across stores)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from app.config import settings

_connections: dict[str, sqlite3.Connection] = {}
_locks: dict[str, threading.RLock] = {}


def get_recommendation_db(db_path: str | None = None) -> tuple[sqlite3.Connection, threading.RLock]:
    path = str(db_path or settings.recommendation_db_path)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    if path not in _connections:
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _connections[path] = conn
        _locks[path] = threading.RLock()

    return _connections[path], _locks[path]


def close_recommendation_db(db_path: str | None = None) -> None:
    path = str(db_path or settings.recommendation_db_path)
    conn = _connections.pop(path, None)
    _locks.pop(path, None)
    if conn is not None:
        conn.close()
