import sqlite3
from pathlib import Path

class SeenStore:
    """Thread-safe, atomic SQLite store to prevent state bloat and race conditions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10.0)

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    composite_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON seen_jobs (source)")

    def is_seen(self, composite_key: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_jobs WHERE composite_key = ?", (composite_key,))
            return cursor.fetchone() is not None

    def filter_unseen(self, jobs: list) -> list:
        """Efficient batch check to avoid 1-by-1 queries."""
        if not jobs:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            keys = [job.composite_key for job in jobs]
            placeholders = ",".join("?" for _ in keys)
            cursor.execute(f"SELECT composite_key FROM seen_jobs WHERE composite_key IN ({placeholders})", keys)
            seen_set = {row[0] for row in cursor.fetchall()}
            return [job for job in jobs if job.composite_key not in seen_set]

    def mark_seen(self, jobs: list) -> None:
        if not jobs:
            return
        with self._get_connection() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO seen_jobs (composite_key, source) VALUES (?, ?)",
                [(job.composite_key, job.source) for job in jobs]
            )