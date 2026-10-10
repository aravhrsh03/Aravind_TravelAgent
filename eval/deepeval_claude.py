"""Claude as the DeepEval judge model (DeepEval defaults to OpenAI; this keeps the stack single-vendor).

Every call is charged against the optional spend cap in `src.services.llm` (estimated from list prices), and the judge
raises `BudgetExceeded` instead of making a call that would go over it.
"""
from __future__ import annotations

from deepeval.models import DeepEvalBaseLLM

from src.config import get_settings
from src.services import llm as llm_mod


class BudgetExceeded(RuntimeError):
    pass


class ClaudeJudge(DeepEvalBaseLLM):
    def __init__(self, model: str | None = None):
        self.model_id = model or get_settings().llm_model
        self.calls = 0
        super().__init__(self.model_id)

    def load_model(self):
        import anthropic

        return anthropic.Anthropic(max_retries=3)

    def _guard(self) -> None:
        if llm_mod.over_budget(llm_mod.get_llm().cost_usd):
            raise BudgetExceeded(f"spend cap ${llm_mod.SPEND_CAP_USD} reached")

    def _charge(self, resp) -> None:
        usage = getattr(resp, "usage", None)
        if usage is not None:
            pin, pout = llm_mod.PRICES.get(self.model_id, (0.0, 0.0))
            llm_mod.EXTERNAL_SPEND_USD += (usage.input_tokens * pin + usage.output_tokens * pout) / 1_000_000
        self.calls += 1

    def generate(self, prompt: str, schema=None):
        self._guard()
        client = self.model
        if schema is not None:  # DeepEval passes a pydantic model when it wants structured output
            resp = client.messages.parse(model=self.model_id, max_tokens=4000, output_format=schema,
                                         messages=[{"role": "user", "content": prompt}])
            self._charge(resp)
            return resp.parsed_output
        resp = client.messages.create(model=self.model_id, max_tokens=4000, output_config={"effort": "low"},
                                      messages=[{"role": "user", "content": prompt}])
        self._charge(resp)
        return "".join(b.text for b in resp.content if b.type == "text")

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return f"anthropic/{self.model_id}"
