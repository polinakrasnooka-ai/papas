"""SQLite-backed dedupe state.

Tracks TED notice IDs we've already qualified and posted, so a cron re-run
doesn't re-post the same tender. Also records SKIP decisions and brief
contents for debugging.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class State:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                notice_id TEXT PRIMARY KEY,
                seen_at TEXT NOT NULL,
                outcome TEXT NOT NULL,
                brief TEXT
            )
            """
        )
        self.conn.commit()

    def is_seen(self, notice_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM seen WHERE notice_id = ?", (notice_id,)
        )
        return cur.fetchone() is not None

    def mark(self, notice_id: str, outcome: str, brief: str | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO seen (notice_id, seen_at, outcome, brief) VALUES (?, ?, ?, ?)",
            (notice_id, datetime.now(timezone.utc).isoformat(), outcome, brief),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
