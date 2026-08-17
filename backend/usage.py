"""
Per-user lifetime usage limits for the analyze endpoints.

Backed by a small SQLite file (config.USAGE_DB_PATH) so the count survives
process restarts and is shared across gunicorn workers. Admin callers
(role == "admin") are unlimited; everyone else is capped at
config.USER_ANALYSIS_LIMIT, for life (no periodic reset).

user_id/role are trusted, client-supplied values — this service has no auth
of its own, so this is a product-level cap, not a security boundary.
"""

from __future__ import annotations

import sqlite3
import threading

import config

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.USAGE_DB_PATH, timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS usage (user_id TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)")
    return conn


def get_count(user_id: str) -> int:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT count FROM usage WHERE user_id = ?", (user_id,)).fetchone()
        return row[0] if row else 0


def increment(user_id: str) -> int:
    """Atomically bump user_id's count by 1 and return the new total."""
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO usage (user_id, count) VALUES (?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET count = count + 1",
            (user_id,),
        )
        conn.commit()
        row = conn.execute("SELECT count FROM usage WHERE user_id = ?", (user_id,)).fetchone()
        return row[0]


def usage_info(user_id: str, role: str) -> dict:
    """{used, limit, remaining, unlimited} — limit/remaining are None when unlimited."""
    unlimited = role == "admin"
    used = 0 if unlimited else get_count(user_id)
    return {
        "used": used,
        "limit": None if unlimited else config.USER_ANALYSIS_LIMIT,
        "remaining": None if unlimited else max(0, config.USER_ANALYSIS_LIMIT - used),
        "unlimited": unlimited,
    }


def check_limit(user_id: str, role: str) -> None:
    """Raises usage.LimitReached if a non-admin caller is already at/over the cap."""
    if role == "admin":
        return
    used = get_count(user_id)
    if used >= config.USER_ANALYSIS_LIMIT:
        raise LimitReached(used, config.USER_ANALYSIS_LIMIT)


class LimitReached(Exception):
    def __init__(self, used: int, limit: int):
        self.used = used
        self.limit = limit
        super().__init__(f"Analysis limit reached ({used}/{limit}).")
