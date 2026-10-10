"""ChromaDB persistent vector store with metadata filtering."""
from __future__ import annotations

from functools import lru_cache

import logging

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import get_settings
from src.rag.embeddings import embed

logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)  # chroma 1.0 posthog client is noisy/broken


@lru_cache
def get_collection():
    s = get_settings()
    client = chromadb.PersistentClient(path=str(s.chroma_dir), settings=ChromaSettings(anonymized_telemetry=False))
    return client.get_or_create_collection(s.collection_name, metadata={"hnsw:space": "cosine"})


def upsert(ids: list[str], docs: list[str], metas: list[dict], batch: int = 2000) -> None:
    col = get_collection()
    vecs = embed(docs)
    for i in range(0, len(ids), batch):
        col.upsert(ids=ids[i:i + batch], documents=docs[i:i + batch], metadatas=metas[i:i + batch],
                   embeddings=vecs[i:i + batch].tolist())


def dense_search(query: str, n: int, where: dict | None) -> list[tuple[str, float]]:
    """Returns [(id, cosine_similarity)] best first."""
    col = get_collection()
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=embed([query]).tolist(), n_results=min(n, col.count()), where=where or None,
                    include=["distances"])
    return [(i, 1.0 - d) for i, d in zip(res["ids"][0], res["distances"][0])]


def build_where(filters: dict) -> dict | None:
    """Translate API filters into a Chroma `where` clause."""
    clauses: list[dict] = []
    for key, field in (("destinations", "destination"), ("travel_types", "travel_type"),
                       ("budget_tiers", "budget_tier"), ("regions", "region"), ("categories", "category")):
        vals = filters.get(key)
        if vals:
            clauses.append({field: {"$in": list(vals)}})
    if filters.get("min_rating") is not None:
        clauses.append({"rating": {"$gte": int(filters["min_rating"])}})
    if filters.get("max_spend_per_day") is not None:
        clauses.append({"spend_per_day_usd": {"$lte": float(filters["max_spend_per_day"])}})
    if filters.get("months"):
        clauses.append({"visit_month": {"$in": [int(m) for m in filters["months"]]}})
    if filters.get("min_days") is not None:
        clauses.append({"duration_days": {"$gte": int(filters["min_days"])}})
    if filters.get("max_days") is not None:
        clauses.append({"duration_days": {"$lte": int(filters["max_days"])}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}
