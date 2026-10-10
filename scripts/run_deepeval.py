"""Budget-capped DeepEval run with Claude as the judge.

    python scripts/run_deepeval.py --budget 2.0 --cases 0,1,4

Why a separate script: the full suite in run_eval.py runs 8 Claude plans and about 70 judge calls (roughly $3). This one
keeps every existing offline result and adds only the Claude-judged part, on a few scenarios, under a hard spend cap:

  * the cap is estimated from list prices (src/services/llm.py::PRICES) and shared by the planning agents and the judge;
  * DeepEval runs ONE case at a time and sequentially, so the cap is checked before every call;
  * when the cap is reached the run stops cleanly and reports only the cases that finished.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "eval"))

from src.services import llm as llm_mod  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=2.0, help="hard cap in USD (estimated from list prices)")
    ap.add_argument("--cases", default="0,1,4", help="indexes into PLAN_QUERIES to evaluate")
    ap.add_argument("--append", action="store_true",
                    help="merge these cases into the existing DeepEval results instead of replacing them")
    args = ap.parse_args()
    llm_mod.SPEND_CAP_USD = args.budget

    import run_eval as ev  # noqa: E402  (heavy imports happen here)
    from deepeval import evaluate
    from deepeval.evaluate.configs import AsyncConfig, DisplayConfig
    from deepeval.metrics import AnswerRelevancyMetric, ContextualRelevancyMetric, FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    from deepeval_claude import BudgetExceeded, ClaudeJudge

    from src.agents.orchestrator import get_orchestrator
    from src.rag.corpus import get_corpus
    from src.services.llm import get_llm

    llm = get_llm()
    if not llm.online:
        raise SystemExit("Claude is not available (no key or no credits); nothing to evaluate.")

    def spent() -> float:
        return llm.cost_usd + llm_mod.EXTERNAL_SPEND_USD

    idx = [int(i) for i in args.cases.split(",")]
    results_path = ev.OUT / "latest_results.json"
    report = json.loads(results_path.read_text(encoding="utf-8"))
    old_deep = report.get("deepeval") if args.append and report.get("deepeval", {}).get("status") == "ok" else None
    old_plans = (report.get("plans_claude") or {}).get("plans", []) if old_deep else []
    if old_deep:  # skip scenarios that were already evaluated
        done_q = {x["query"] for x in old_plans}
        idx = [i for i in idx if ev.PLAN_QUERIES[i] not in done_q]
        if not idx:
            raise SystemExit("All requested cases are already in the results.")

    # ---- 1. real Claude plans for the chosen scenarios
    states, rows = [], []
    for i in idx:
        q = ev.PLAN_QUERIES[i]
        t0 = time.perf_counter()
        st = get_orchestrator().plan(q, {})
        dt = time.perf_counter() - t0
        if not st.judge or st.judge["engine"] != "llm":
            print(f"scenario {i}: Claude was not used (cap reached or API problem); stopping the planning phase")
            break
        it = st.itinerary
        rows.append({"query": q, "destination": it["destination"], "judge_overall": st.judge["overall"],
                     "passed": st.judge["passed"], "revisions": st.revisions, "citation_coverage": it["citation_coverage"],
                     "budget_status": it["cost"]["budget_status"], "latency_s": round(dt, 1), "itinerary_engine": it.get("engine")})
        states.append(st)
        print(f"plan {i}: {it['destination']} judge={st.judge['overall']} passed={st.judge['passed']} rev={st.revisions} "
              f"({dt:.0f}s)  spent~${spent():.2f}")
    if not states:
        raise SystemExit("No Claude plans were produced.")

    # ---- 2. DeepEval, one case at a time
    judge = ClaudeJudge()
    corpus = get_corpus()
    per_metric: dict[str, list] = {}
    done, stopped = 0, None
    for st in states:
        ctx_ids = {e for d in st.itinerary["days"] for i in d["items"] for e in i.get("evidence", [])}
        ctx = [corpus.get(i)[0] for i in list(ctx_ids)[:12] if i in corpus.id_to_pos] or [h.text for h in st.hits[:8]]
        case = LLMTestCase(input=st.query, actual_output=ev.render_plan(st), retrieval_context=ctx)
        metrics = [
            AnswerRelevancyMetric(model=judge, threshold=0.6, async_mode=False),
            FaithfulnessMetric(model=judge, threshold=0.6, async_mode=False),
            ContextualRelevancyMetric(model=judge, threshold=0.5, async_mode=False),
            GEval(name="Recommendation quality", model=judge, threshold=0.6, async_mode=False,
                  criteria="Does the itinerary satisfy the traveler's stated interests, trip length, party type and "
                           "budget, with a realistic pace and specific, useful activities?",
                  evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT]),
        ]
        try:
            res = evaluate(test_cases=[case], metrics=metrics, async_config=AsyncConfig(run_async=False),
                           display_config=DisplayConfig(show_indicator=False, print_results=False))
        except BudgetExceeded as e:
            stopped = str(e)
            print("stopping DeepEval:", e)
            break
        except Exception as e:  # a metric failing on one case should not lose the finished ones
            if "BudgetExceeded" in type(e).__name__ or "spend cap" in str(e):
                stopped = str(e)
                print("stopping DeepEval:", e)
                break
            raise
        for tr in res.test_results:
            for md in tr.metrics_data:
                per_metric.setdefault(md.name, []).append((md.score or 0.0, bool(md.success)))
        done += 1
        print(f"deepeval case {done}/{len(states)} done  spent~${spent():.2f}")

    new_metrics = {k: {"n": len(v), "mean_score": float(np.mean([s for s, _ in v])),
                       "passes": int(sum(p for _, p in v))} for k, v in per_metric.items()}
    merged: dict[str, dict] = {}
    for k in set(new_metrics) | set((old_deep or {}).get("metrics", {})):
        n_old = (old_deep or {}).get("n", 0) if old_deep and k in old_deep["metrics"] else 0
        m_old = old_deep["metrics"][k]["mean_score"] if n_old else 0.0
        pr_old = old_deep["metrics"][k]["pass_rate"] if n_old else 0.0
        nn = new_metrics.get(k, {"n": 0, "mean_score": 0.0, "passes": 0})
        n = n_old + nn["n"]
        merged[k] = {"mean_score": round((m_old * n_old + nn["mean_score"] * nn["n"]) / n, 3),
                     "pass_rate": round((pr_old * n_old + nn["passes"]) / n, 3)}
    n_total = (old_deep or {}).get("n", 0) + done
    prior_spend = (report.get("plans_claude") or {}).get("estimated_spend_usd", 0.0) if old_deep else 0.0
    deep = {"status": "ok" if n_total else "skipped", "judge_model": judge.get_model_name(), "n": n_total,
            "metrics": merged, "estimated_spend_usd": round(prior_spend + spent(), 3), "stopped_early": stopped,
            "reason": stopped or "no DeepEval case finished"}
    report["llm"] = llm.status()
    report["deepeval"] = deep
    report["plans_claude"] = {"plans": old_plans + rows, "spend_cap_usd": args.budget,
                              "estimated_spend_usd": round(prior_spend + spent(), 3)}
    results_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    summary_path = ev.OUT / "latest_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["deepeval"] = deep["metrics"] or deep["reason"]
    all_rows = report["plans_claude"]["plans"]
    summary["claude_plans_mean_judge"] = round(float(np.mean([r["judge_overall"] for r in all_rows])), 2)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    ev.write_report(report)
    print(json.dumps({"deepeval": deep, "claude_plans": rows}, indent=2))
    print(f"\nEstimated total spend: ${spent():.2f} (cap ${args.budget})")


if __name__ == "__main__":
    main()
