"""Shared blackboard state + agent base class.

Agents communicate through a shared `TripState` (blackboard pattern): each agent reads what earlier
agents wrote, adds its own output, and posts a message addressed to the next agent. Every step is
timed and recorded so the UI can show the full "planning council" trace.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TripState:
    query: str
    params: dict[str, Any] = field(default_factory=dict)  # explicit overrides from the API/UI
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    guardrail: dict | None = None
    profile: dict | None = None
    filters: dict = field(default_factory=dict)
    relaxations: list[str] = field(default_factory=list)
    hits: list = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    feasibility: dict | None = None
    itinerary: dict | None = None
    judge: dict | None = None
    revision_feedback: dict | None = None
    revisions: int = 0
    trace: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    blocked: bool = False

    def post(self, sender: str, recipient: str, content: str) -> None:
        self.messages.append({"from": sender, "to": recipient, "content": content})


class Agent:
    name = "agent"
    role = ""

    def __init__(self) -> None:
        from src.services.llm import get_llm

        self.llm = get_llm()

    def run(self, state: TripState) -> TripState:
        t0 = time.perf_counter()
        calls, failures = self.llm.calls, self.llm.failures
        summary, details = self.act(state)
        llm_ok = self.llm.calls > calls and self.llm.failures == failures
        state.trace.append({
            "agent": self.name, "role": self.role, "summary": summary,
            "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
            "engine": "llm" if llm_ok else "deterministic",
            "details": details,
        })
        return state

    def act(self, state: TripState) -> tuple[str, dict]:  # pragma: no cover - abstract
        raise NotImplementedError
