"""REST endpoints (all under /api/v1)."""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from src.agents.base import TripState
from src.agents.orchestrator import get_orchestrator
from src.api.schemas import (CompareRequest, FeasibilityRequest, FeedbackRequest, QueryRequest, SearchRequest,
                             SuitabilityRequest, TwinsRequest)
from src.config import DIMENSIONS
from src.rag.corpus import get_corpus
from src.rag.hybrid_retriever import hybrid_search
from src.services import feasibility as feas
from src.services import insights, learning
from src.services.catalog import get_catalog
from src.services.feedback_store import get_feedback_store
from src.services.llm import get_llm
from src.services.suitability_model import predict
from src.utils.guardrails import check_query

router = APIRouter(prefix="/api/v1")


# ------------------------------------------------------------------ helpers
def _params(req: QueryRequest) -> dict:
    return req.params.model_dump(exclude_none=True)


def _guard(state: TripState) -> None:
    if state.blocked:
        raise HTTPException(status_code=400, detail={"error": "blocked", "request_id": state.request_id,
                                                     "category": state.guardrail["category"],
                                                     "reasons": state.guardrail["reasons"]})


def _log(endpoint: str, state: TripState | None, t0: float, query: str | None = None, payload: dict | None = None) -> float:
    ms = (time.perf_counter() - t0) * 1000
    judge = state.judge["overall"] if state and state.judge else None
    get_feedback_store().log_request(state.request_id if state else f"{endpoint}-{time.time_ns()}", endpoint,
                                     query or (state.query if state else None), ms, judge,
                                     get_llm().status()["provider"], bool(state and state.blocked), payload)
    return round(ms, 1)


def _dna_from(query: str | None, dna: dict | None) -> dict:
    if dna:
        return {d: float(dna.get(d, 0.5)) for d in DIMENSIONS}
    if not query:
        raise HTTPException(400, detail="Provide either `query` or `dna`.")
    state = get_orchestrator().classify(query, {})
    _guard(state)
    return state.profile["dna"]


def _destination_summaries(hits) -> list[dict]:
    groups = defaultdict(list)
    for h in hits:
        groups[h.meta["destination"]].append(h)
    out = []
    cat = get_catalog()
    for dest, hs in groups.items():
        d = cat.get(dest)
        s = insights.summarize_reviews([h.text for h in hs], [a.name for a in d.activities] if d else [], top=3)
        out.append({"destination": dest, "matches": len(hs), "avg_rating": round(sum(h.meta["rating"] for h in hs) / len(hs), 2),
                    "best_priority": round(max(h.scores["priority"] for h in hs), 3), **s})
    return sorted(out, key=lambda x: x["best_priority"], reverse=True)


# ------------------------------------------------------------------ core
@router.post("/search", tags=["retrieval"], summary="Hybrid semantic + keyword search over historical trips")
def search(req: SearchRequest):
    t0 = time.perf_counter()
    state = get_orchestrator().classify(req.query, _params(req))
    _guard(state)
    filters = req.filters.model_dump(exclude_none=True)
    hits = hybrid_search(state.query, filters, req.top_k, dna=state.profile["dna"] if req.personalize else None, mode=req.mode)
    ms = _log("search", state, t0)
    return {"request_id": state.request_id, "query": state.query, "guardrail": state.guardrail,
            "traveler_dna": state.profile["dna"], "segment": state.profile["segment"], "filters_applied": filters,
            "mode": req.mode, "results": [h.to_dict() for h in hits], "destination_summaries": _destination_summaries(hits),
            "latency_ms": ms}


@router.post("/classify", tags=["agents"], summary="Travel preference classification + Traveler DNA scoring")
def classify(req: QueryRequest):
    t0 = time.perf_counter()
    state = get_orchestrator().classify(req.query, _params(req))
    _guard(state)
    ms = _log("classify", state, t0)
    return {"request_id": state.request_id, "profile": state.profile, "guardrail": state.guardrail,
            "trace": state.trace, "latency_ms": ms}


@router.post("/recommend", tags=["agents"], summary="Prioritized destination + activity recommendations")
def recommend(req: QueryRequest):
    t0 = time.perf_counter()
    state = get_orchestrator().recommend(req.query, _params(req))
    _guard(state)
    ms = _log("recommend", state, t0, payload={"profile": state.profile})
    return {"request_id": state.request_id, "profile": state.profile, "recommendations": state.candidates,
            "retrieval": {"filters": state.filters, "relaxed": state.relaxations,
                          "evidence": [h.to_dict() for h in state.hits]},
            "trace": state.trace, "messages": state.messages, "latency_ms": ms}


@router.post("/plan", tags=["agents"], summary="Full multi-agent trip plan with itinerary, feasibility and judge")
def plan(req: QueryRequest):
    t0 = time.perf_counter()
    state = get_orchestrator().plan(req.query, _params(req))
    _guard(state)
    ms = _log("plan", state, t0, payload={"profile": state.profile})
    return {"request_id": state.request_id, "profile": state.profile, "guardrail": state.guardrail,
            "recommendations": state.candidates, "plan": state.feasibility, "itinerary": state.itinerary,
            "judge": state.judge, "revisions": state.revisions,
            "retrieval": {"filters": state.filters, "relaxed": state.relaxations,
                          "evidence": [h.to_dict() for h in state.hits]},
            "trace": state.trace, "messages": state.messages, "llm": get_llm().status(), "latency_ms": ms}


# ------------------------------------------------------------------ analysis tools
@router.post("/feasibility", tags=["analysis"], summary="Budget and duration feasibility for a destination")
def feasibility(req: FeasibilityRequest):
    dest = get_catalog().get(req.destination)
    if not dest:
        raise HTTPException(404, detail=f"Unknown destination '{req.destination}'. See GET /api/v1/destinations.")
    return feas.analyze(dest, req.days, req.travelers, req.budget_tier, req.budget_usd, req.origin_region, req.month)


@router.post("/suitability", tags=["analysis"], summary="Predict itinerary suitability (P(rating >= 4)) with explanation")
def suitability(req: SuitabilityRequest):
    dest = get_catalog().get(req.destination)
    if not dest:
        raise HTTPException(404, detail=f"Unknown destination '{req.destination}'.")
    dna = _dna_from(req.query, req.dna)
    return {"traveler_dna": dna, **predict(dna, dest, req.travel_type, req.budget_tier, req.month, req.days).to_dict()}


@router.post("/compare", tags=["analysis"], summary="Destination comparison: which did similar travelers rate higher?")
def compare(req: CompareRequest):
    dna = _dna_from(req.query, req.dna)
    try:
        result = insights.duel(dna, req.destinations[0], req.destinations[1], req.travel_type)
    except ValueError as e:
        raise HTTPException(404, detail=str(e)) from e
    return {"traveler_dna": dna, **result}


@router.post("/twins", tags=["analysis"], summary="Travel Twins: most similar historical travelers and their favourites")
def twins(req: TwinsRequest):
    dna = _dna_from(req.query, req.dna)
    tw = insights.find_twins(dna, req.k)
    df = get_corpus().df
    trips = df[df["user_id"].isin(tw["user_id"])]
    out = []
    for r in tw.itertuples():
        t = trips[trips["user_id"] == r.user_id].sort_values("rating", ascending=False)
        out.append({"user_id": r.user_id, "similarity": round(r.similarity, 3), "source_dataset": r.source_dataset,
                    "dna": {d: round(getattr(r, f"pref_{d}"), 3) for d in DIMENSIONS},
                    "trips": t[["review_id", "destination", "rating", "travel_type", "title"]].to_dict("records")})
    stats = insights.twin_destination_stats(dna, k=400)
    return {"traveler_dna": dna, "twins": out, "twin_favourites": stats.head(8).to_dict("records")}


# ------------------------------------------------------------------ feedback loop + catalog + ops
@router.post("/feedback", tags=["feedback"], summary="Rate a recommendation; feeds ranking boosts and the knowledge base")
def feedback(req: FeedbackRequest):
    if not get_catalog().get(req.destination):
        raise HTTPException(404, detail=f"Unknown destination '{req.destination}'.")
    comment = req.comment
    if comment:
        g = check_query(f"travel feedback: {comment}")
        if g.category in ("injection", "harmful"):
            raise HTTPException(400, detail={"error": "blocked", "reasons": g.reasons})
        comment = g.sanitized_query.removeprefix("travel feedback: ")
    store = get_feedback_store()
    req_log = store.get_request(req.request_id) if req.request_id else None
    query = req_log["query"] if req_log else None
    profile = (req_log.get("payload") or {}).get("profile") if req_log else None
    fid = store.add_feedback(req.request_id, query, get_catalog().get(req.destination).name, req.rating, req.helpful,
                             comment, req.travel_type)
    learned = learning.ingest(fid, req.destination, req.rating, comment, req.travel_type, profile)
    return {"feedback_id": fid, "new_ranking_boost": round(store.destination_boosts().get(get_catalog().get(req.destination).name, 0), 3),
            "indexed_as_experience": learned}


@router.get("/feedback/stats", tags=["feedback"], summary="Feedback statistics and learned ranking boosts")
def feedback_stats():
    return get_feedback_store().stats()


@router.get("/destinations", tags=["catalog"], summary="List destinations in the knowledge base")
def destinations():
    df = get_corpus().df
    agg = df.groupby("destination")["rating"].agg(["count", "mean"])
    return [{"name": d.name, "country": d.country, "region": d.region, "summary": d.summary,
             "reviews": int(agg.loc[d.name, "count"]) if d.name in agg.index else 0,
             "avg_rating": round(float(agg.loc[d.name, "mean"]), 2) if d.name in agg.index else None,
             "daily_cost": d.daily_cost, "best_months": d.best_months, "strengths": d.strengths}
            for d in get_catalog().destinations]


@router.get("/destinations/{name}", tags=["catalog"], summary="Destination overview with review summary")
def destination(name: str):
    out = insights.destination_overview(name)
    if not out:
        raise HTTPException(404, detail=f"Unknown destination '{name}'.")
    return out


@router.get("/experiences/{review_id}", tags=["catalog"], summary="Fetch one historical experience (citation lookup)")
def experience(review_id: str):
    corpus = get_corpus()
    if review_id not in corpus.id_to_pos:
        raise HTTPException(404, detail=f"Unknown review id '{review_id}'.")
    text, meta = corpus.get(review_id)
    return {"review_id": review_id, "text": text, **meta}


@router.get("/metrics", tags=["ops"], summary="Request, latency, judge-score and LLM usage metrics")
def metrics():
    return {**get_feedback_store().metrics(), "llm": get_llm().status(), "feedback": get_feedback_store().stats()["total_feedback"]}
