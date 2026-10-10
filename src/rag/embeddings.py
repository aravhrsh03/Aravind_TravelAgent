"""Local sentence-transformer embeddings (no API cost, works offline after first download)."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from src.config import get_settings


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


def embed(texts: list[str], batch_size: int = 64) -> np.ndarray:
    return _model().encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 500)


@lru_cache
def _reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(get_settings().reranker_model)


def rerank_scores(query: str, docs: list[str]) -> np.ndarray | None:
    """Cross-encoder relevance scores, or None when the reranker is disabled/unavailable."""
    if not get_settings().use_reranker or not docs:
        return None
    try:
        return np.asarray(_reranker().predict([(query, d) for d in docs]), dtype=float)
    except Exception:  # model download failure etc. -> degrade gracefully to fused ranking
        return None
