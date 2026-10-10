from __future__ import annotations

from src.agents.base import Agent, TripState
from src.services.catalog import get_catalog
from src.utils.guardrails import check_numbers, check_query


class GuardrailAgent(Agent):
    name = "Guardrail"
    role = "Validates input, blocks prompt injection / harmful / off-topic requests, redacts PII"

    def act(self, state: TripState) -> tuple[str, dict]:
        res = check_query(state.query, get_catalog().names())
        problems = check_numbers(state.params.get("budget_usd"), state.params.get("days"), state.params.get("travelers"))
        if problems and res.allowed:
            res.allowed = False
            res.category = "invalid_parameters"
            res.reasons = problems
        state.guardrail = res.to_dict()
        state.blocked = not res.allowed
        if res.allowed:
            state.query = res.sanitized_query
            state.post(self.name, "PreferenceClassifier", "Query validated" + (f"; redacted {res.redactions}" if res.redactions else ""))
            return "Input accepted" + (" (PII redacted)" if res.redactions else ""), state.guardrail
        return f"Blocked: {res.category}", state.guardrail
