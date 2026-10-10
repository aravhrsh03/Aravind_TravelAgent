"""Destination & activity recommendation with prioritization.

Destination priority = weighted blend of five independent signals (each 0-1):
    evidence     Bayesian, similarity-weighted rating of retrieved trips + Travel-Twin ratings
    preference   Traveler-DNA x destination-strength match
    suitability  ML-predicted P(rating >= 4) for this exact trip (season, budget, length, party)
    feasibility  budget / duration / season feasibility score
    feedback     learned boost from user feedback on past recommendations
"""
from __future__ import annotations

import re

import numpy as np

from src.agents.base import Agent, TripState
from src.config import DIMENSIONS
from src.rag.corpus import get_corpus
from src.services import feasibility as feas
from src.services.catalog import Destination, get_catalog
from src.services.dataset_builder import preference_match
from src.services.feedback_store import get_feedback_store
from src.services.insights import bayes, twin_destination_stats
from src.services.suitability_model import predict

WEIGHTS = {"evidence": 0.25, "preference": 0.25, "suitability": 0.25, "feasibility": 0.15, "feedback": 0.10}
_POS = re.compile(r"highlight|loved|exceeded|do not miss|best part|worth", re.I)


def activity_evidence(dest: str, activity: str, travel_type: str, prefer_ids: set[str], k: int = 2) -> list[str]:
    """Review IDs where travelers praised this activity (same trip type and retrieved trips first)."""
    df = get_corpus().df
    g = df[(df["destination"] == dest) & (df["rating"] >= 4) & df["review_text"].str.contains(activity, regex=False)]
    if g.empty:
        return []
    pos = g[g["review_text"].apply(lambda t: any(activity in s and _POS.search(s) for s in re.split(r"(?<=[.!?])\s+", t)))]
    if pos.empty:
        return []
    order = pos.assign(_r=pos["review_id"].isin(prefer_ids).astype(int) * 2 + (pos["travel_type"] == travel_type).astype(int))
    return order.sort_values(["_r", "rating"], ascending=False)["review_id"].head(k).tolist()


def rank_activities(dest: Destination, prof: dict, prefer_ids: set[str], must_cover: list[str] | None = None) -> list[dict]:
    dna = prof["dna"]
    out = []
    per_day_budget = (prof["budget_usd"] / prof["days"] / prof["travelers"]) if prof.get("budget_usd") else None
    for a in dest.activities:
        ev = activity_evidence(dest.name, a.name, prof["travel_type"], prefer_ids)
        score = 0.65 * dna.get(a.dimension, 0.3) + 0.25 * min(len(ev), 2) / 2
        if per_day_budget and a.cost > 0.6 * per_day_budget:
            score -= 0.15  # expensive relative to the daily budget
        if prof["travel_type"] == "family" and a.dimension == "nightlife":
            score -= 0.3
        if must_cover and a.dimension in must_cover:
            score += 0.3
        if a.hours > 24 and prof["days"] < 7:
            score -= 1.0  # multi-day treks don't fit short trips
        out.append({"activity": a.name, "dimension": a.dimension, "cost_usd": a.cost, "hours": a.hours,
                    "score": round(score, 3), "evidence": ev})
    return sorted(out, key=lambda x: x["score"], reverse=True)


class RecommenderAgent(Agent):
    name = "Recommender"
    role = "Scores and prioritizes destinations and activities from evidence, preferences, ML and feasibility"

    def act(self, state: TripState) -> tuple[str, dict]:
        prof, cat = state.profile, get_catalog()
        dna_vec = np.array([prof["dna"][d] for d in DIMENSIONS])
        corpus_df = get_corpus().df
        prior = float(corpus_df["rating"].mean())

        if prof["destinations"]:
            names = list(prof["destinations"])
        else:  # score the whole catalog (within requested regions): cheap, surfaces less-obvious affordable places
            regions = prof.get("regions") or []
            names = [d.name for d in cat.destinations if not regions or d.region in regions] or cat.names()
        twins = twin_destination_stats(prof["dna"], k=400, travel_type=prof["travel_type"])
        twin_map = twins.set_index("destination").to_dict("index") if len(twins) else {}
        boosts = get_feedback_store().destination_boosts()

        cands = []
        for name in names:
            dest = cat.get(name)
            if not dest:
                continue
            dh = [h for h in state.hits if h.meta["destination"] == dest.name]
            if dh:
                w = np.array([h.scores["relevance"] for h in dh])
                r = np.array([h.meta["rating"] for h in dh], dtype=float)
                hit_rating = bayes(float((w * r).sum() / w.sum()), len(dh), prior)
            else:
                hit_rating = None
            twin_rating = twin_map.get(dest.name, {}).get("bayes_rating")
            ev_parts = [x for x in (hit_rating, twin_rating) if x is not None]
            evidence_rating = float(np.mean(ev_parts)) if ev_parts else prior
            suit = predict(prof["dna"], dest, prof["travel_type"], prof["budget_tier"], prof["month"], prof["days"])
            fz = feas.analyze(dest, prof["days"], prof["travelers"], prof["budget_tier"], prof["budget_usd"],
                              prof["origin_region"], prof["month"])
            if fz["budget_status"] == "over_budget" and fz["recommended_tier"]:
                # Score the destination as the FeasibilityAnalyst would plan it: at the best tier that fits.
                fz = feas.analyze(dest, prof["days"], prof["travelers"], fz["recommended_tier"], prof["budget_usd"],
                                  prof["origin_region"], prof["month"])
                fz["feasibility_score"] = round(max(0.0, fz["feasibility_score"] - 0.1), 2)
                fz["notes"].insert(0, f"Fits the budget at {fz['estimate']['tier']} tier (requested {prof['budget_tier']}).")
            signals = {"evidence": (evidence_rating - 1) / 4, "preference": preference_match(dna_vec, dest),
                       "suitability": suit.probability, "feasibility": fz["feasibility_score"],
                       "feedback": (boosts.get(dest.name, 0.0) + 1) / 2}
            priority = sum(WEIGHTS[k] * v for k, v in signals.items())
            cands.append({"destination": dest.name, "country": dest.country, "region": dest.region,
                          "summary": dest.summary, "priority": round(priority, 4),
                          "signals": {k: round(v, 3) for k, v in signals.items()},
                          "evidence_rating": round(evidence_rating, 2), "retrieved_trips": len(dh),
                          "twin_reviews": int(twin_map.get(dest.name, {}).get("twin_reviews", 0)),
                          "suitability": suit.to_dict(), "feasibility": fz, "reasons": []})
        cands.sort(key=lambda c: c["priority"], reverse=True)
        cands = cands[: state.params.get("max_destinations", 5)]

        prefer_ids = {h.meta["review_id"] for h in state.hits}
        for i, c in enumerate(cands):
            c["rank"] = i + 1
            c["label"] = "Top pick" if i == 0 else ("Budget alternative" if c["feasibility"]["estimate"]["total"] <
                                                    cands[0]["feasibility"]["estimate"]["total"] * 0.75 else "Strong alternative")
            c["activities"] = rank_activities(get_catalog().get(c["destination"]), prof, prefer_ids)[:6]
            c["reasons"] = self._reasons(c, prof)
        state.candidates = cands
        top = cands[0] if cands else None
        if top:
            state.post(self.name, "FeasibilityAnalyst",
                       f"Top pick {top['destination']} (priority {top['priority']:.2f}); {len(cands) - 1} alternatives")
        return (f"Top pick: {top['destination']}" if top else "No candidates"), {
            "weights": WEIGHTS, "ranking": [{k: c[k] for k in ("destination", "priority", "signals", "label")} for c in cands]}

    @staticmethod
    def _reasons(c: dict, prof: dict) -> list[str]:
        s, out = c["signals"], []
        if c["twin_reviews"]:
            out.append(f"{c['twin_reviews']} travelers with a similar profile rated it {c['evidence_rating']:.1f}/5 "
                       f"(adjusted for review count)")
        if s["preference"] >= 0.65:
            out.append(f"Strong match for {', '.join(prof['top_preferences'])}")
        out.append(f"Predicted satisfaction {c['suitability']['probability'] * 100:.0f}% ({c['suitability']['label']})")
        fz = c["feasibility"]
        if fz["budget_status"] != "unknown":
            out.append(f"Estimated ${fz['estimate']['total']:,} for the trip: {fz['budget_status'].replace('_', ' ')}")
        if fz["in_season"] is False:
            out.append("Outside its best season")
        if s["feedback"] > 0.55:
            out.append("Rated well by WanderVision users' feedback")
        return out
