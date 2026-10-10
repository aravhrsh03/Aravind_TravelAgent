"""Orchestrator: runs the multi-agent planning workflow.

    Guardrail -> PreferenceClassifier -> Retriever -> Recommender -> FeasibilityAnalyst
              -> ItineraryPlanner -> Critic --(fails rubric, max N times)--> FeasibilityAnalyst/ItineraryPlanner

The critic's verdict is turned into structured revision feedback (missing preferences to cover,
cheaper tier) so the revision loop changes something concrete instead of re-rolling.
"""
from __future__ import annotations

import time

from src.agents.base import TripState
from src.agents.critic_agent import CriticAgent
from src.agents.feasibility_agent import FeasibilityAgent
from src.agents.guardrail_agent import GuardrailAgent
from src.agents.itinerary_agent import ItineraryAgent
from src.agents.preference_agent import PreferenceAgent
from src.agents.recommender_agent import RecommenderAgent
from src.agents.retrieval_agent import RetrievalAgent
from src.config import BUDGET_TIERS, get_settings


class Orchestrator:
    def __init__(self) -> None:
        self.guard, self.pref, self.retr = GuardrailAgent(), PreferenceAgent(), RetrievalAgent()
        self.rec, self.feas, self.itin, self.critic = RecommenderAgent(), FeasibilityAgent(), ItineraryAgent(), CriticAgent()

    def _front(self, state: TripState, retrieve: bool = True) -> bool:
        self.guard.run(state)
        if state.blocked:
            return False
        self.pref.run(state)
        if retrieve:
            self.retr.run(state)
        return True

    def search(self, query: str, params: dict) -> TripState:
        state = TripState(query=query, params=params)
        self._front(state)
        return state

    def classify(self, query: str, params: dict) -> TripState:
        state = TripState(query=query, params=params)
        self._front(state, retrieve=False)
        return state

    def recommend(self, query: str, params: dict) -> TripState:
        state = TripState(query=query, params=params)
        if self._front(state):
            self.rec.run(state)
        return state

    def plan(self, query: str, params: dict) -> TripState:
        t0 = time.perf_counter()
        state = TripState(query=query, params=params)
        if not self._front(state):
            return state
        self.rec.run(state)
        self.feas.run(state)
        self.itin.run(state)
        self.critic.run(state)
        while state.judge and not state.judge["passed"] and state.revisions < get_settings().max_revisions:
            state.revisions += 1
            state.revision_feedback = self._feedback(state)
            state.post("Orchestrator", "FeasibilityAnalyst", f"Revision {state.revisions}: {state.revision_feedback}")
            self.feas.run(state)
            self.itin.run(state)
            self.critic.run(state)
        state.trace.append({"agent": "Orchestrator", "role": "Coordinates agents and the revision loop",
                            "summary": f"Done in {(time.perf_counter() - t0):.1f}s with {state.revisions} revision(s)",
                            "duration_ms": round((time.perf_counter() - t0) * 1000, 1), "engine": "deterministic",
                            "details": {}})
        return state

    @staticmethod
    def _feedback(state: TripState) -> dict:
        j, fb = state.judge, {"issues": state.judge["issues"]}
        if j["checks"]["missing_preferences"]:
            fb["must_cover"] = j["checks"]["missing_preferences"]
        if j["checks"]["budget_status"] == "over_budget":
            cur = state.feasibility["tier"]
            fb["tier"] = BUDGET_TIERS[max(0, BUDGET_TIERS.index(cur) - 1)]
        return fb


_orch: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch
