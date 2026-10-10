"""Turns experience records into retrievable chunks.

Chunking strategy: reviews in this corpus are short (60-120 words), so each review is ONE chunk,
prefixed with a structured header (destination, trip type, duration, budget, month, activities).
The header lets both BM25 and the embedding model match on facts like "family" or "7 days"
that the free text may not state. For external corpora with long reviews, `split_long_text`
produces sentence-window chunks (~120 words, 1-sentence overlap) that share the same header.
"""
from __future__ import annotations

import re

import pandas as pd

MAX_WORDS = 120
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

METADATA_FIELDS = ["review_id", "user_id", "destination", "country", "region", "category", "rating",
                   "travel_type", "visit_month", "duration_days", "budget_tier", "spend_per_day_usd", "visit_date",
                   "source_dataset"]


def header(row: pd.Series | dict) -> str:
    month = _MONTHS[int(row["visit_month"]) - 1] if row.get("visit_month") else ""
    return (f"{row['destination']}, {row['country']} | {row['travel_type']} trip | {row['duration_days']} days | "
            f"{row['budget_tier']}-tier budget | {month} | focus: {row['category']} | activities: {row.get('activities', '')}")


def split_long_text(text: str, max_words: int = MAX_WORDS) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, cur = [], []
    for s in sentences:
        if cur and len(" ".join(cur + [s]).split()) > max_words:
            chunks.append(" ".join(cur))
            cur = cur[-1:]  # one-sentence overlap keeps context across chunk boundaries
        cur.append(s)
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def to_chunks(df: pd.DataFrame) -> tuple[list[str], list[str], list[dict]]:
    ids, docs, metas = [], [], []
    for row in df.to_dict("records"):
        body = f"{row['title']}. {row['review_text']}"
        pieces = [body] if len(body.split()) <= MAX_WORDS * 1.5 else split_long_text(body)
        for i, piece in enumerate(pieces):
            ids.append(row["review_id"] if len(pieces) == 1 else f"{row['review_id']}#{i}")
            docs.append(f"{header(row)}\n{piece}")
            metas.append({k: row[k] for k in METADATA_FIELDS if k in row and pd.notna(row[k])})
    return ids, docs, metas
