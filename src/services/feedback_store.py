"""SQLite-backed feedback loop + request log.

Feedback adjusts ranking through a shrunk per-destination boost:
    boost(d) = sum((rating_i - 3) / 2) / (n_d + PRIOR)    in (-1, 1)
PRIOR damps the effect of the first few votes so one angry user can't bury a destination.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from functools import lru_cache

from src.config import get_settings

PRIOR = 5.0


class FeedbackStore:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, request_id TEXT, query TEXT,
            destination TEXT, rating INTEGER, helpful INTEGER, comment TEXT, travel_type TEXT);
        CREATE TABLE IF NOT EXISTS requests (
            request_id TEXT PRIMARY KEY, ts REAL, endpoint TEXT, query TEXT, latency_ms REAL,
            judge_score REAL, provider TEXT, blocked INTEGER, payload TEXT);
        """)
        self._boost_cache: dict[str, float] | None = None

    # ---------------- feedback
    def add_feedback(self, request_id: str | None, query: str | None, destination: str, rating: int,
                     helpful: bool | None, comment: str | None, travel_type: str | None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO feedback (ts, request_id, query, destination, rating, helpful, comment, travel_type) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (time.time(), request_id, query, destination, rating, None if helpful is None else int(helpful),
                 comment, travel_type))
            self.conn.commit()
            self._boost_cache = None
            return int(cur.lastrowid)

    def destination_boosts(self) -> dict[str, float]:
        if self._boost_cache is None:
            rows = self.conn.execute(
                "SELECT destination, SUM((rating - 3) / 2.0), COUNT(*) FROM feedback GROUP BY destination").fetchall()
            self._boost_cache = {d: s / (n + PRIOR) for d, s, n in rows}
        return self._boost_cache

    def stats(self) -> dict:
        total, avg = self.conn.execute("SELECT COUNT(*), AVG(rating) FROM feedback").fetchone()
        helpful = self.conn.execute("SELECT AVG(helpful) FROM feedback WHERE helpful IS NOT NULL").fetchone()[0]
        per_dest = self.conn.execute(
            "SELECT destination, COUNT(*), AVG(rating) FROM feedback GROUP BY destination ORDER BY COUNT(*) DESC").fetchall()
        boosts = self.destination_boosts()
        recent = self.conn.execute(
            "SELECT ts, destination, rating, helpful, comment FROM feedback ORDER BY id DESC LIMIT 10").fetchall()
        return {
            "total_feedback": total, "avg_rating": round(avg, 2) if avg else None,
            "helpful_rate": round(helpful, 3) if helpful is not None else None,
            "per_destination": [{"destination": d, "count": n, "avg_rating": round(a, 2),
                                 "ranking_boost": round(boosts.get(d, 0.0), 3)} for d, n, a in per_dest],
            "recent": [{"ts": t, "destination": d, "rating": r, "helpful": h, "comment": c} for t, d, r, h, c in recent],
        }

    # ---------------- request log / observability
    def log_request(self, request_id: str, endpoint: str, query: str | None, latency_ms: float,
                    judge_score: float | None, provider: str, blocked: bool, payload: dict | None = None) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO requests VALUES (?,?,?,?,?,?,?,?,?)",
                (request_id, time.time(), endpoint, query, latency_ms, judge_score, provider, int(blocked),
                 json.dumps(payload, default=str) if payload else None))
            self.conn.commit()

    def get_request(self, request_id: str) -> dict | None:
        row = self.conn.execute("SELECT query, payload FROM requests WHERE request_id=?", (request_id,)).fetchone()
        if not row:
            return None
        return {"query": row[0], "payload": json.loads(row[1]) if row[1] else None}

    def metrics(self) -> dict:
        rows = self.conn.execute(
            "SELECT endpoint, COUNT(*), AVG(latency_ms), AVG(judge_score), SUM(blocked) FROM requests GROUP BY endpoint").fetchall()
        return {"endpoints": [{"endpoint": e, "requests": n, "avg_latency_ms": round(l or 0, 1),
                               "avg_judge_score": round(j, 2) if j else None, "blocked": b} for e, n, l, j, b in rows]}


@lru_cache
def get_feedback_store() -> FeedbackStore:
    s = get_settings()
    s.processed_dir.mkdir(parents=True, exist_ok=True)
    return FeedbackStore(str(s.feedback_db))
