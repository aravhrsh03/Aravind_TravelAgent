"""Collaborative insights over historical travelers.

* Travel Twins     - nearest historical travelers by Traveler-DNA (cosine on centred preference vectors)
* Destination Duel - head-to-head comparison of destinations as rated by *similar* travelers
* Review summaries - extractive praise / complaint mining from retrieved reviews
"""
from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache

import numpy as np
import pandas as pd

from src.config import DIMENSIONS, get_settings
from src.rag.corpus import get_corpus
from src.services.catalog import get_catalog

BAYES_C = 8  # prior strength (in reviews) for Bayesian-average ratings

_POS = re.compile(r"\b(highlight|loved|exceeded|do not miss|best part|perfect|worth it|worth every|great value|"
                  r"highly recommend|kid-friendly|buzzing|comfortable|go back|10/10|great time)\b", re.I)
_NEG = re.compile(r"\b(disappointing|skip|letdown|mistake|ruined|expensive|overpriced|rushed|not ideal|"
                  r"would not recommend|unpleasant|overrated|crowded|tourist trap|ran out|closed|not for us)\b", re.I)


@lru_cache
def _profiles() -> tuple[pd.DataFrame, np.ndarray]:
    prof = pd.read_csv(get_settings().travelers_path)
    m = prof[[f"pref_{d}" for d in DIMENSIONS]].to_numpy() - 0.5
    m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
    return prof, m


def _centred(dna: dict[str, float]) -> np.ndarray:
    v = np.array([dna.get(d, 0.5) for d in DIMENSIONS]) - 0.5
    return v / (np.linalg.norm(v) + 1e-9)


def find_twins(dna: dict[str, float], k: int = 25) -> pd.DataFrame:
    prof, m = _profiles()
    sims = m @ _centred(dna)
    idx = np.argsort(-sims)[:k]
    out = prof.iloc[idx].copy()
    out["similarity"] = sims[idx]
    return out


def bayes(mean: float, n: float, prior: float) -> float:
    return (BAYES_C * prior + mean * n) / (BAYES_C + n)


def twin_destination_stats(dna: dict[str, float], k: int = 400, travel_type: str | None = None) -> pd.DataFrame:
    """Per-destination ratings given by the k most similar travelers (similarity-weighted)."""
    twins = find_twins(dna, k)
    df = get_corpus().df
    trips = df[df["user_id"].isin(twins["user_id"])].merge(twins[["user_id", "similarity"]], on="user_id")
    if travel_type:
        same = trips[trips["travel_type"] == travel_type]
        trips = same if len(same) >= 40 else trips  # fall back if too few same-type trips
    prior = float(df["rating"].mean())
    rows = []
    for dest, g in trips.groupby("destination"):
        w = g["similarity"].clip(lower=0.05)
        wmean = float((g["rating"] * w).sum() / w.sum())
        rows.append({"destination": dest, "twin_reviews": len(g), "twin_avg_rating": round(float(g["rating"].mean()), 2),
                     "weighted_rating": round(wmean, 2), "bayes_rating": round(bayes(wmean, len(g), prior), 3),
                     "pct_4plus": round(float((g["rating"] >= 4).mean()), 3)})
    return pd.DataFrame(rows).sort_values("bayes_rating", ascending=False) if rows else pd.DataFrame()


def summarize_reviews(texts: list[str], activity_names: list[str] | None = None, top: int = 4) -> dict:
    """Extractive summary: most praised activities, recurring complaints and representative quotes."""
    praised, panned, complaints = Counter(), Counter(), Counter()
    for t in texts:
        for sent in re.split(r"(?<=[.!?])\s+", t):
            pos, neg = bool(_POS.search(sent)), bool(_NEG.search(sent))
            for a in activity_names or []:
                if a.lower() in sent.lower():
                    if pos and not neg:
                        praised[a] += 1
                    elif neg:
                        panned[a] += 1
            if neg:
                low = sent.lower()
                if any(w in low for w in ("weather", "rain", "season", "seas", "closed")):
                    complaints["off-season weather"] += 1
                elif any(w in low for w in ("expensive", "overpriced", "costs", "prices")):
                    complaints["high costs"] += 1
                elif "rushed" in low or "too short" in low:
                    complaints["trip too short"] += 1
                elif "too long" in low or "ran out" in low:
                    complaints["trip too long"] += 1
                elif "crowded" in low or "tourist trap" in low or "overrated" in low:
                    complaints["crowds / tourist traps"] += 1
                elif "children" in low:
                    complaints["not child-friendly"] += 1
    return {"praised_activities": [{"activity": a, "mentions": n} for a, n in praised.most_common(top)],
            "panned_activities": [{"activity": a, "mentions": n} for a, n in panned.most_common(top)],
            "common_complaints": [{"issue": a, "mentions": n} for a, n in complaints.most_common(top)]}


def destination_overview(name: str) -> dict | None:
    dest = get_catalog().get(name)
    if not dest:
        return None
    df = get_corpus().df
    g = df[df["destination"] == dest.name]
    prior = float(df["rating"].mean())
    by_type = g.groupby("travel_type")["rating"].agg(["count", "mean"]).round(2).reset_index().to_dict("records")
    summary = summarize_reviews(g["review_text"].tolist(), [a.name for a in dest.activities])
    return {"destination": dest.name, "country": dest.country, "region": dest.region, "summary": dest.summary,
            "reviews": len(g), "avg_rating": round(float(g["rating"].mean()), 2) if len(g) else None,
            "bayes_rating": round(bayes(float(g["rating"].mean()), len(g), prior), 2) if len(g) else None,
            "by_travel_type": by_type, "best_months": dest.best_months, "daily_cost": dest.daily_cost,
            "strengths": dest.strengths, "ideal_days": dest.ideal_days, **summary}


def duel(dna: dict[str, float], a: str, b: str, travel_type: str | None = None) -> dict:
    """Which destination did travelers *like this one* rate higher?"""
    cat = get_catalog()
    da, db = cat.get(a), cat.get(b)
    if not da or not db:
        raise ValueError(f"Unknown destination(s): {[x for x, d in ((a, da), (b, db)) if not d]}")
    df = get_corpus().df
    prior = float(df["rating"].mean())
    stats = twin_destination_stats(dna, k=1200, travel_type=travel_type)
    out = {}
    for d in (da, db):
        row = stats[stats["destination"] == d.name]
        g = df[df["destination"] == d.name]
        twin = row.iloc[0].to_dict() if len(row) else {"twin_reviews": 0, "weighted_rating": None, "bayes_rating": prior,
                                                        "pct_4plus": None}
        out[d.name] = {
            "similar_travelers": {k: twin.get(k) for k in ("twin_reviews", "weighted_rating", "bayes_rating", "pct_4plus")},
            "all_travelers": {"reviews": len(g), "avg_rating": round(float(g["rating"].mean()), 2)},
            **summarize_reviews(g["review_text"].tolist(), [x.name for x in d.activities], top=3),
        }
    sa, sb = out[da.name]["similar_travelers"]["bayes_rating"], out[db.name]["similar_travelers"]["bayes_rating"]
    winner = da.name if sa >= sb else db.name
    margin = abs(sa - sb)
    confidence = "high" if margin > 0.3 else "medium" if margin > 0.12 else "low (near tie)"
    return {"destinations": out, "winner": winner, "margin": round(margin, 3), "confidence": confidence}
