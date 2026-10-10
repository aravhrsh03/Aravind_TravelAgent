"""Hybrid retrieval: dense (Chroma) + keyword (BM25) -> Reciprocal Rank Fusion -> cross-encoder
rerank -> recommendation prioritization (relevance x rating x preference fit x feedback)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.config import DIMENSIONS, get_settings
from src.rag import vector_store
from src.rag.corpus import get_corpus
from src.rag.embeddings import rerank_scores
from src.services.catalog import get_catalog
from src.services.dataset_builder import preference_match
from src.services.feedback_store import get_feedback_store


@dataclass
class Hit:
    review_id: str
    text: str
    meta: dict
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"review_id": self.review_id, "text": self.text, **self.meta,
                "scores": {k: round(v, 4) for k, v in self.scores.items()}}


def rrf(rankings: list[list[str]], k: int) -> dict[str, float]:
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return fused


def hybrid_search(query: str, filters: dict | None = None, top_k: int | None = None,
                  dna: dict[str, float] | None = None, mode: str = "hybrid") -> list[Hit]:
    """mode: hybrid | dense | keyword (the latter two exist for ablation/evaluation)."""
    s = get_settings()
    filters = filters or {}
    top_k = top_k or s.default_top_k
    corpus = get_corpus()

    dense = vector_store.dense_search(query, s.candidate_pool, vector_store.build_where(filters)) if mode != "keyword" else []
    keyword = corpus.keyword_search(query, s.candidate_pool, filters) if mode != "dense" else []
    dense_map, kw_map = dict(dense), dict(keyword)
    fused = rrf([[c for c, _ in dense], [c for c, _ in keyword]], s.rrf_k)
    cands = sorted(fused, key=fused.get, reverse=True)[: max(top_k * 3, 30)]
    cands = [c for c in cands if c in corpus.id_to_pos]  # feedback docs may exist only after reload
    if not cands:
        return []

    docs = [corpus.get(c)[0] for c in cands]
    ce = rerank_scores(query, docs) if mode == "hybrid" else None
    # Min-max within the candidate set: raw cross-encoder sigmoids saturate near 1.0 and would
    # stop discriminating, letting the rating term dominate prioritization.
    r = ce if ce is not None else np.array([fused[c] for c in cands])
    relevance = (r - r.min()) / (r.max() - r.min() + 1e-9) * 0.9 + 0.1

    catalog = get_catalog()
    boosts = get_feedback_store().destination_boosts()
    dna_vec = np.array([dna.get(d, 0.5) for d in DIMENSIONS]) if dna else None

    hits = []
    for i, cid in enumerate(cands):
        text, meta = corpus.get(cid)
        dest = catalog.get(meta["destination"])
        rating_s = (float(meta["rating"]) - 1) / 4
        pref_s = preference_match(dna_vec, dest) if (dna_vec is not None and dest) else 0.5
        fb_s = (boosts.get(meta["destination"], 0.0) + 1) / 2
        final = (s.w_relevance * relevance[i] + s.w_rating * rating_s + s.w_preference * pref_s + s.w_feedback * fb_s)
        hits.append(Hit(cid, text, meta, {
            "dense": dense_map.get(cid, 0.0), "bm25": kw_map.get(cid, 0.0), "rrf": fused[cid],
            "relevance": float(relevance[i]), "rating": rating_s, "preference_fit": pref_s,
            "feedback": fb_s, "priority": float(final)}))
    hits.sort(key=lambda h: h.scores["priority"], reverse=True)
    return hits[:top_k]
