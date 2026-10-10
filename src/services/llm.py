"""LLM gateway.

Every agent asks this gateway for structured JSON. With credentials it calls Claude through the
official Anthropic SDK (structured outputs + server-side refusal fallback). Without credentials, or
on any API failure, it returns None and the calling agent uses its deterministic offline logic -
so the whole system (API, UI, evaluation) always runs end-to-end.
"""
from __future__ import annotations

import json
import logging
import time
from functools import lru_cache

from src.config import get_settings

log = logging.getLogger("wandervision.llm")

# USD per million tokens (input, output) - first-party API list prices
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0), "claude-sonnet-5-5": (2.0, 10.0),
          "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0), "claude-fable-5-1": (10.0, 50.0)}

# Optional hard spend cap (USD), shared by the gateway and the DeepEval judge. Off by default; scripts/run_deepeval.py
# sets it so an evaluation run can never exceed a chosen budget (estimated from list prices above).
SPEND_CAP_USD: float | None = None
EXTERNAL_SPEND_USD = 0.0  # spend by other Claude callers in the same process (the DeepEval judge)


def over_budget(gateway_cost: float = 0.0) -> bool:
    return SPEND_CAP_USD is not None and gateway_cost + EXTERNAL_SPEND_USD >= SPEND_CAP_USD


class LLMGateway:
    def __init__(self) -> None:
        s = get_settings()
        self.model = s.llm_model
        self.provider = s.resolved_provider
        self.client = None
        self.calls = 0
        self.failures = 0
        self.input_tokens = 0
        self.output_tokens = 0  # includes the model's internal reasoning tokens (billed as output)
        self.last_error: str | None = None
        if self.provider == "anthropic":
            try:
                import anthropic

                self.client = anthropic.Anthropic(timeout=s.llm_timeout_s, max_retries=2)
            except Exception as e:  # SDK missing or misconfigured -> offline
                log.warning("Anthropic client unavailable (%s); running offline", e)
                self.provider = "offline"

    @property
    def online(self) -> bool:
        return self.client is not None

    def json(self, system: str, user: str, schema: dict, effort: str = "low", max_tokens: int = 8000) -> dict | None:
        """Return a dict matching `schema`, or None (offline / refusal / error)."""
        if not self.online:
            return None
        if over_budget(self.cost_usd):
            return self._fail("spend cap reached; using deterministic logic")
        import anthropic

        self.calls += 1
        t0 = time.time()
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as e:
            return self._fail(f"rate limited: {e}")
        except anthropic.APIStatusError as e:
            if e.status_code in (401, 403) or "credit balance" in str(e.message).lower():
                # Account-level problem (bad key, no credits): retrying every call only adds latency and noise.
                # Trip the breaker so the rest of this process runs on the deterministic agents.
                self.client = None
                log.error("LLM disabled for this process (%s); using deterministic agents", e.message)
            return self._fail(f"API error {e.status_code}: {e.message}")
        except anthropic.APIConnectionError as e:
            return self._fail(f"connection error: {e}")
        if resp.stop_reason == "refusal":
            return self._fail("model declined the request")
        if resp.stop_reason == "max_tokens":
            return self._fail("response truncated (max_tokens)")
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            out = json.loads(text)
        except json.JSONDecodeError:
            return self._fail("invalid JSON from model")
        self.input_tokens += resp.usage.input_tokens
        self.output_tokens += resp.usage.output_tokens
        log.info("LLM call ok in %.1fs (%s in / %s out tokens)", time.time() - t0,
                 resp.usage.input_tokens, resp.usage.output_tokens)
        return out

    def _fail(self, msg: str) -> None:
        self.failures += 1
        self.last_error = msg
        log.warning("LLM fallback to offline logic: %s", msg)
        return None

    @property
    def cost_usd(self) -> float:
        pin, pout = PRICES.get(self.model, (0.0, 0.0))
        return (self.input_tokens * pin + self.output_tokens * pout) / 1_000_000

    def status(self) -> dict:
        return {"provider": self.provider if self.online else "offline", "model": self.model if self.online else None,
                "calls": self.calls, "failures": self.failures, "last_error": self.last_error,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "est_cost_usd": round(self.cost_usd, 4)}


@lru_cache
def get_llm() -> LLMGateway:
    return LLMGateway()


def strict_schema(properties: dict, required: list[str] | None = None) -> dict:
    """Object schema in the shape structured outputs require (all keys required, no extras)."""
    return {"type": "object", "properties": properties, "required": required or list(properties),
            "additionalProperties": False}
