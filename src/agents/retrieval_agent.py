"""Retrieval agent: query expansion + metadata filters + progressive filter relaxation."""
from __future__ import annotations

from src.agents.base import Agent, TripState
from src.rag.hybrid_retriever import hybrid_search

MIN_EVIDENCE = 8
_DIM_WORDS = {"beach": "beach sea snorkelling", "culture": "sightseeing temples museums history",
              "food": "local food street food cuisine", "nightlife": "nightlife bars party",
              "nature": "nature hiking scenery", "shopping": "shopping markets", "wellness": "spa relaxing massage",
              "family": "kids family-friendly"}


class RetrievalAgent(Agent):
    name = "Retriever"
    role = "Hybrid (BM25 + dense) retrieval of similar historical trips with metadata filtering"

    def act(self, state: TripState) -> tuple[str, dict]:
        prof = state.profile
        explicit = dict(state.params.get("filters") or {})  # user-set filters are never relaxed
        expanded = " ".join([state.query, prof["travel_type"], "trip"] + [_DIM_WORDS[d] for d in prof["top_preferences"]])

        soft: list[tuple[str, dict]] = [
            ("travel type", {"travel_types": [prof["travel_type"]]}),
            ("budget tier", {"budget_tiers": [prof["budget_tier"]]}),
            ("rating >= 4", {"min_rating": 4}),
        ]
        if prof["destinations"]:
            explicit.setdefault("destinations", prof["destinations"])
        elif prof.get("regions"):
            explicit.setdefault("regions", prof["regions"])

        top_k = state.params.get("top_k", 12)
        hits, relaxed = [], []
        for n_relax in range(len(soft) + 1):
            filters = dict(explicit)
            for _, f in soft[n_relax:]:
                for k, v in f.items():
                    filters.setdefault(k, v)
            hits = hybrid_search(expanded, filters, top_k=top_k, dna=prof["dna"])
            if len(hits) >= MIN_EVIDENCE or n_relax == len(soft):
                break
            relaxed.append(soft[n_relax][0])
        state.filters, state.relaxations, state.hits = filters, relaxed, hits

        dests = sorted({h.meta["destination"] for h in hits})
        state.post(self.name, "Recommender", f"{len(hits)} similar trips across {len(dests)} destinations"
                   + (f" (relaxed: {', '.join(relaxed)})" if relaxed else ""))
        return (f"Retrieved {len(hits)} trips" + (f"; relaxed {', '.join(relaxed)}" if relaxed else ""),
                {"expanded_query": expanded, "filters": filters, "relaxed": relaxed, "destinations": dests,
                 "hits": [h.to_dict() for h in hits[:5]]})
