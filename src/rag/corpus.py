"""In-memory corpus (source of truth for metadata) + BM25 keyword index."""
from __future__ import annotations

import re
import threading
from functools import lru_cache

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from src.config import get_settings
from src.rag.documents import to_chunks

_STOP = set("""a an the and or but if of to in on at for with by from as is was were be been it its this that these those
i we you he she they my our your their me us them so very too just than then there here what which who whom
had has have do did does not no can could would should will about into over after before again all any more most
some such only own same also""".split())


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    # light suffix stripping so "beaches"/"beach", "kids"/"kid" match without a full stemmer
    out = []
    for t in toks:
        if t in _STOP:
            continue
        for suf in ("es", "s"):
            if len(t) > 4 and t.endswith(suf) and not t.endswith("ss"):
                t = t[: -len(suf)]
                break
        out.append(t)
    return out


class Corpus:
    def __init__(self, df: pd.DataFrame):
        self._lock = threading.Lock()
        self.df = df.reset_index(drop=True)
        self.ids, self.docs, self.metas = to_chunks(self.df)
        self._rebuild()

    def _rebuild(self) -> None:
        self.id_to_pos = {cid: i for i, cid in enumerate(self.ids)}
        self.meta_df = pd.DataFrame(self.metas)
        self.bm25 = BM25Okapi([tokenize(d) for d in self.docs])

    def add(self, rows: pd.DataFrame) -> list[str]:
        """Append new experiences (e.g. from the feedback loop) to the keyword index."""
        with self._lock:
            ids, docs, metas = to_chunks(rows)
            self.df = pd.concat([self.df, rows], ignore_index=True)
            self.ids += ids
            self.docs += docs
            self.metas += metas
            self._rebuild()
        return ids

    def mask(self, filters: dict) -> np.ndarray:
        m = self.meta_df
        keep = np.ones(len(m), dtype=bool)
        for key, field in (("destinations", "destination"), ("travel_types", "travel_type"),
                           ("budget_tiers", "budget_tier"), ("regions", "region"), ("categories", "category")):
            if filters.get(key):
                keep &= m[field].isin(filters[key]).to_numpy()
        if filters.get("min_rating") is not None:
            keep &= (m["rating"] >= filters["min_rating"]).to_numpy()
        if filters.get("max_spend_per_day") is not None:
            keep &= (m["spend_per_day_usd"] <= filters["max_spend_per_day"]).to_numpy()
        if filters.get("months"):
            keep &= m["visit_month"].isin(filters["months"]).to_numpy()
        if filters.get("min_days") is not None:
            keep &= (m["duration_days"] >= filters["min_days"]).to_numpy()
        if filters.get("max_days") is not None:
            keep &= (m["duration_days"] <= filters["max_days"]).to_numpy()
        return keep

    def keyword_search(self, query: str, n: int, filters: dict) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        scores = np.where(self.mask(filters), scores, -np.inf)
        top = np.argsort(-scores)[:n]
        return [(self.ids[i], float(scores[i])) for i in top if np.isfinite(scores[i]) and scores[i] > 0]

    def get(self, chunk_id: str) -> tuple[str, dict]:
        i = self.id_to_pos[chunk_id]
        return self.docs[i], self.metas[i]


@lru_cache
def get_corpus() -> Corpus:
    s = get_settings()
    if not s.experiences_path.exists():
        raise FileNotFoundError("Corpus missing - run `python scripts/build_dataset.py` then `python scripts/build_index.py`.")
    return Corpus(pd.read_csv(s.experiences_path))
