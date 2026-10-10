"""Feedback loop, part 2: turning validated feedback into new retrievable experiences.

Part 1 (ranking boosts) lives in FeedbackStore. Here, positive feedback with a substantive comment
becomes a new travel experience in both indexes, so the next traveler with similar needs can
retrieve it. Comments pass the same guardrails as queries (injection check + PII redaction) before
they are indexed, so the feedback channel cannot be used to poison the knowledge base.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from src.rag import vector_store
from src.rag.corpus import get_corpus
from src.services.catalog import get_catalog
from src.services.feedback_store import get_feedback_store
from src.utils.guardrails import check_query

log = logging.getLogger("wandervision.learning")
MIN_COMMENT_WORDS = 8


def _row(fid: int, destination: str, rating: int, comment: str, travel_type: str | None, profile: dict | None) -> dict:
    dest = get_catalog().get(destination)
    today = dt.date.today()
    profile = profile or {}
    return {
        "review_id": f"F{fid:05d}", "user_id": "wandervision_user", "destination": dest.name, "country": dest.country,
        "region": dest.region, "category": (profile.get("top_preferences") or ["culture"])[0], "rating": rating,
        "title": "WanderVision traveler feedback", "review_text": comment,
        "travel_type": travel_type or profile.get("travel_type", "solo"), "visit_date": today.isoformat(),
        "visit_month": profile.get("month") or today.month, "duration_days": profile.get("days", dest.ideal_days),
        "budget_tier": profile.get("budget_tier", "mid"), "spend_per_day_usd": dest.daily_cost[profile.get("budget_tier", "mid")],
        "trip_cost_usd": None, "activities": "", "home_region": profile.get("origin_region") or "",
        "source_dataset": "wandervision_feedback",
    }


def ingest(fid: int, destination: str, rating: int, comment: str | None, travel_type: str | None,
           profile: dict | None) -> str | None:
    """Index the feedback as an experience if it qualifies. Returns the new review_id or None."""
    if rating < 4 or not comment or len(comment.split()) < MIN_COMMENT_WORDS or not get_catalog().get(destination):
        return None
    g = check_query(f"travel review: {comment}")
    if not g.allowed:
        log.warning("feedback %s rejected by guardrails: %s", fid, g.category)
        return None
    row = _row(fid, destination, rating, g.sanitized_query.removeprefix("travel review: "), travel_type, profile)
    ids = get_corpus().add(pd.DataFrame([row]))
    corpus = get_corpus()
    vector_store.upsert(ids, [corpus.get(i)[0] for i in ids], [corpus.get(i)[1] for i in ids])
    return ids[0]


def restore() -> int:
    """On startup, re-add previously learned experiences to the in-memory keyword index."""
    store = get_feedback_store()
    rows = store.conn.execute("SELECT id, destination, rating, comment, travel_type FROM feedback "
                              "WHERE rating >= 4 AND comment IS NOT NULL").fetchall()
    corpus = get_corpus()
    new_rows = []
    for fid, dest, rating, comment, tt in rows:
        if f"F{fid:05d}" in corpus.id_to_pos or len((comment or "").split()) < MIN_COMMENT_WORDS:
            continue
        g = check_query(f"travel review: {comment}")
        if g.allowed and get_catalog().get(dest):
            new_rows.append(_row(fid, dest, rating, g.sanitized_query.removeprefix("travel review: "), tt, None))
    if new_rows:  # one batch -> one BM25 rebuild
        corpus.add(pd.DataFrame(new_rows))
    return len(new_rows)
