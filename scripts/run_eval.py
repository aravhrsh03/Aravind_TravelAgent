"""Offline + LLM evaluation suite. Writes eval/results/*.json and eval/results/Evaluation_Report.md.

    python scripts/run_eval.py              # all sections (DeepEval runs only if Claude credentials exist)
    python scripts/run_eval.py --skip-deepeval

Sections
  1. Retrieval ablation: keyword vs dense vs hybrid vs hybrid+rerank (P@5, P@10, MRR, nDCG@10)
  2. Preference classification accuracy (travel type, top dims, days, budget, tier)
  3. Guardrail red-team: block rate on attacks, false-positive rate on benign queries
  4. End-to-end plans: judge scores, pass rate, citation coverage, constraint satisfaction, latency
  5. DeepEval (LLM-as-judge with Claude): answer relevancy, faithfulness, contextual relevancy, G-Eval quality
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.orchestrator import get_orchestrator  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.rag.corpus import get_corpus  # noqa: E402
from src.rag.hybrid_retriever import hybrid_search  # noqa: E402
from src.services.catalog import get_catalog  # noqa: E402
from src.services.llm import get_llm  # noqa: E402
from src.utils.guardrails import check_query  # noqa: E402

DS = ROOT / "eval" / "datasets"
OUT = ROOT / "eval" / "results"
PLAN_QUERIES = [
    "A couple wants a 5-day trip focused on beaches, sightseeing and local food in December, budget $3000, flying from India",
    "Family of 4 with two kids, limited budget of $2500, 6 days, want highly rated activities and kid-friendly places",
    "Solo traveler from Europe, 7 days in October, loves hiking, nature and history, budget-friendly",
    "Group of 4 friends, 5 days of nightlife, beaches and street food in March, total budget 4800 USD",
    "Luxury honeymoon with spa and beaches for 6 days in February, budget 8000 USD, from India",
    "Retired couple, 8 days of culture, museums and food in Europe in May, mid-range, budget 6000 USD, from North America",
    "Business traveler with 3 free days in Tokyo, wants food and culture",
    "3 friends, adventure and nature, 9 days in January, flying from Oceania, budget 9000 USD",
]


# ------------------------------------------------------------------ 1. retrieval
def _is_relevant(meta: dict, rule: dict) -> bool:
    dest = get_catalog().get(meta["destination"])
    r = meta["rating"]
    if "travel_type" in rule and meta["travel_type"] not in rule["travel_type"]:
        return False
    if "budget_tier" in rule and meta["budget_tier"] not in rule["budget_tier"]:
        return False
    if "min_rating" in rule and r < rule["min_rating"]:
        return False
    if "max_rating" in rule and r > rule["max_rating"]:
        return False
    if "dest_dim" in rule and dest.strengths[rule["dest_dim"]] < rule["min_strength"]:
        return False
    if "max_dest_mid_cost" in rule and dest.daily_cost["mid"] > rule["max_dest_mid_cost"]:
        return False
    if "min_dest_mid_cost" in rule and dest.daily_cost["mid"] < rule["min_dest_mid_cost"]:
        return False
    if rule.get("off_season") and meta["visit_month"] in dest.best_months:
        return False
    if rule.get("short_trip") and meta["duration_days"] >= dest.min_days:
        return False
    return True


def _metrics(rels: list[bool], k_list=(5, 10)) -> dict:
    out = {f"P@{k}": float(np.mean(rels[:k])) if rels else 0.0 for k in k_list}
    first = next((i for i, x in enumerate(rels) if x), None)
    out["MRR"] = 1.0 / (first + 1) if first is not None else 0.0
    dcg = sum(1 / np.log2(i + 2) for i, x in enumerate(rels[:10]) if x)
    idcg = sum(1 / np.log2(i + 2) for i in range(min(10, max(sum(rels), 1))))
    out["nDCG@10"] = dcg / idcg if idcg else 0.0
    return out


def eval_retrieval() -> dict:
    cases = json.loads((DS / "retrieval_cases.json").read_text())
    s = get_settings()
    configs = [("keyword (BM25)", "keyword", False), ("dense (MiniLM)", "dense", False),
               ("hybrid (RRF)", "hybrid", False), ("hybrid + cross-encoder rerank", "hybrid", True)]
    results = {}
    for label, mode, rerank in configs:
        s.use_reranker = rerank
        rows, lat = [], []
        for c in cases:
            t0 = time.perf_counter()
            hits = hybrid_search(c["query"], {}, top_k=10, mode=mode)
            lat.append((time.perf_counter() - t0) * 1000)
            rows.append(_metrics([_is_relevant(h.meta, c["relevant"]) for h in hits]))
        results[label] = {k: round(float(np.mean([r[k] for r in rows])), 3) for k in rows[0]}
        results[label]["latency_ms_p50"] = round(statistics.median(lat), 1)
    s.use_reranker = True
    return results


# ------------------------------------------------------------------ 2. preference classification
def eval_preferences() -> dict:
    cases = json.loads((DS / "preference_cases.json").read_text(encoding="utf-8"))
    orch = get_orchestrator()
    acc = {"travel_type": [], "top_dims_recall": [], "days": [], "budget": [], "tier": [], "month": [], "absent": []}
    failures = []
    for c in cases:
        prof = orch.classify(c["query"], {}).profile
        ranked = sorted(prof["dna"], key=prof["dna"].get, reverse=True)[: max(3, len(c["top"]))]
        acc["travel_type"].append(prof["travel_type"] == c["travel_type"])
        acc["top_dims_recall"].append(sum(d in ranked for d in c["top"]) / len(c["top"]))
        acc["days"].append(prof["days"] == c["days"])
        if "budget_usd" in c:
            acc["budget"].append(prof["budget_usd"] is not None and abs(prof["budget_usd"] - c["budget_usd"]) / c["budget_usd"] < 0.1)
        if "tier" in c:
            acc["tier"].append(prof["budget_tier"] == c["tier"])
        if "month" in c:
            acc["month"].append(prof["month"] == c["month"])
        if "absent" in c:
            acc["absent"].append(all(prof["dna"][d] < 0.1 for d in c["absent"]))
        if prof["travel_type"] != c["travel_type"] or prof["days"] != c["days"]:
            failures.append({"query": c["query"], "expected": {k: c.get(k) for k in ("travel_type", "days")},
                             "got": {"travel_type": prof["travel_type"], "days": prof["days"]}})
    return {"n": len(cases), "classifier": "llm" if get_llm().online else "lexicon",
            **{f"{k}_accuracy" if k != "top_dims_recall" else k: round(float(np.mean(v)), 3) for k, v in acc.items() if v},
            "failures": failures}


# ------------------------------------------------------------------ 3. guardrails
def eval_guardrails() -> dict:
    cases = json.loads((DS / "guardrail_cases.json").read_text(encoding="utf-8"))
    names = get_catalog().names()
    blocked = [(c, check_query(c["query"], names)) for c in cases["should_block"]]
    passed = [(c, check_query(c["query"], names)) for c in cases["should_pass"]]
    return {
        "attack_block_rate": round(sum(not r.allowed for _, r in blocked) / len(blocked), 3),
        "category_accuracy": round(sum(r.category == c["category"] for c, r in blocked) / len(blocked), 3),
        "benign_pass_rate": round(sum(r.allowed for _, r in passed) / len(passed), 3),
        "pii_redacted_cases": sum(bool(r.redactions) for _, r in passed),
        "misses": [c["query"] for c, r in blocked if r.allowed],
        "false_positives": [c["query"] for c, r in passed if not r.allowed],
    }


# ------------------------------------------------------------------ 4. end-to-end plans
def render_plan(state) -> str:
    it = state.itinerary
    lines = [it["title"], it["overview"]]
    for d in it["days"]:
        lines.append(f"Day {d['day']} ({d['theme']}): " + "; ".join(f"{i['slot']}: {i['activity']}" for i in d["items"]))
    lines.append(f"Estimated cost: ${it['cost']['estimate']['total']:,} ({it['cost']['budget_status']}).")
    lines += it["tips"]
    return "\n".join(lines)


def eval_plans() -> tuple[dict, list]:
    orch = get_orchestrator()
    rows, states = [], []
    for q in PLAN_QUERIES:
        t0 = time.perf_counter()
        st = orch.plan(q, {})
        ms = (time.perf_counter() - t0) * 1000
        it, prof = st.itinerary, st.profile
        rows.append({
            "query": q, "destination": it["destination"], "judge_overall": st.judge["overall"], "passed": st.judge["passed"],
            "scores": st.judge["scores"], "revisions": st.revisions, "citation_coverage": it["citation_coverage"],
            "days_match": len(it["days"]) == st.feasibility["days"], "budget_status": it["cost"]["budget_status"],
            "within_budget": it["cost"]["budget_status"] in ("feasible", "tight", "unknown"),
            "top_prefs_covered": st.judge["checks"]["preference_coverage"], "adjustments": st.feasibility["adjustments"],
            "latency_ms": round(ms), "segment": prof["segment"]})
        states.append(st)
    summary = {
        "n": len(rows), "judge_engine": states[0].judge["engine"],
        "mean_judge_score": round(float(np.mean([r["judge_overall"] for r in rows])), 2),
        "pass_rate": round(float(np.mean([r["passed"] for r in rows])), 3),
        "mean_citation_coverage": round(float(np.mean([r["citation_coverage"] for r in rows])), 3),
        "within_budget_rate": round(float(np.mean([r["within_budget"] for r in rows])), 3),
        "preference_coverage": round(float(np.mean([r["top_prefs_covered"] for r in rows])), 3),
        "latency_ms_p50": round(statistics.median(r["latency_ms"] for r in rows)),
        "latency_ms_max": max(r["latency_ms"] for r in rows), "plans": rows}
    return summary, states


# ------------------------------------------------------------------ 5. DeepEval
def eval_deepeval(states) -> dict:
    if not get_llm().online:
        return {"status": "skipped", "reason": "No Claude credentials (set ANTHROPIC_API_KEY) - DeepEval metrics need an LLM judge."}
    from deepeval import evaluate
    from deepeval.metrics import AnswerRelevancyMetric, ContextualRelevancyMetric, FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    sys.path.insert(0, str(ROOT / "eval"))
    from deepeval_claude import ClaudeJudge

    judge = ClaudeJudge()
    corpus = get_corpus()
    cases = []
    for st in states:
        ctx_ids = {e for d in st.itinerary["days"] for i in d["items"] for e in i.get("evidence", [])}
        ctx = [corpus.get(i)[0] for i in list(ctx_ids)[:12] if i in corpus.id_to_pos] or [h.text for h in st.hits[:8]]
        cases.append(LLMTestCase(input=st.query, actual_output=render_plan(st), retrieval_context=ctx))
    quality = GEval(name="Recommendation quality", model=judge, threshold=0.6,
                    criteria="Does the itinerary satisfy the traveler's stated interests, trip length, party type and "
                             "budget, with a realistic pace and specific, useful activities?",
                    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT])
    metrics = [AnswerRelevancyMetric(model=judge, threshold=0.6), FaithfulnessMetric(model=judge, threshold=0.6),
               ContextualRelevancyMetric(model=judge, threshold=0.5), quality]
    res = evaluate(test_cases=cases, metrics=metrics)
    per_metric: dict[str, list] = {}
    for tr in res.test_results:
        for md in tr.metrics_data:
            per_metric.setdefault(md.name, []).append((md.score or 0.0, md.success))
    return {"status": "ok", "judge_model": judge.get_model_name(), "n": len(cases),
            "metrics": {k: {"mean_score": round(float(np.mean([s for s, _ in v])), 3),
                            "pass_rate": round(float(np.mean([p for _, p in v])), 3)} for k, v in per_metric.items()}}


# ------------------------------------------------------------------ report
def write_report(r: dict) -> None:
    L = ["# WanderVision - Evaluation Report", "", f"Generated: {time.strftime('%Y-%m-%d %H:%M')} · LLM provider: "
         f"{r['llm']['provider']}", "", "## 1. Retrieval ablation (14 labelled queries, top-10)", "",
         "| Configuration | P@5 | P@10 | MRR | nDCG@10 | p50 latency (ms) |", "|---|---|---|---|---|---|"]
    for k, v in r["retrieval"].items():
        L.append(f"| {k} | {v['P@5']} | {v['P@10']} | {v['MRR']} | {v['nDCG@10']} | {v['latency_ms_p50']} |")
    p = r["preferences"]
    L += ["", f"## 2. Preference classification ({p['n']} labelled queries, classifier: {p['classifier']})", "",
          "| Metric | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in p.items() if k not in ("n", "classifier", "failures")]
    L += ["", "> Caveat: these cases were written alongside the keyword lexicon, so offline-classifier scores are "
          "optimistic. Treat them as a regression suite; unseen phrasings will score lower (the LLM classifier "
          "exists to cover them)."]
    g = r["guardrails"]
    L += ["", "## 3. Guardrails red-team", "", "| Metric | Value |", "|---|---|",
          f"| Attack block rate | {g['attack_block_rate']} |", f"| Block-category accuracy | {g['category_accuracy']} |",
          f"| Benign pass rate | {g['benign_pass_rate']} |", f"| Benign queries with PII redacted | {g['pii_redacted_cases']} |"]
    if g["misses"] or g["false_positives"]:
        L += ["", f"Misses: {g['misses']}  ", f"False positives: {g['false_positives']}"]
    e = r["plans"]
    L += ["", f"## 4. End-to-end plans, offline rule-based mode ({e['n']} scenarios, judge: {e['judge_engine']}): secondary regression suite", "",
          "> The rule-based judge is lenient by design. The primary quality evidence is the Claude-judged section (5b) and DeepEval (5).", "",
          "| Metric | Value |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in e.items() if k not in ("plans", "n", "judge_engine")]
    L += ["", "| Query | Destination | Judge | Citations | Budget | Latency (ms) |", "|---|---|---|---|---|---|"]
    L += [f"| {x['query'][:70]}... | {x['destination']} | {x['judge_overall']} | {x['citation_coverage']} | "
          f"{x['budget_status']} | {x['latency_ms']} |" for x in e["plans"]]
    d = r["deepeval"]
    L += ["", "## 5. DeepEval (LLM-as-judge)", ""]
    if d["status"] == "ok":
        L += [f"Judge model: {d['judge_model']} · {d['n']} test cases", "", "| Metric | Mean score | Pass rate |", "|---|---|---|"]
        L += [f"| {k} | {v['mean_score']} | {v['pass_rate']} |" for k, v in d["metrics"].items()]
    else:
        L.append(f"Skipped: {d['reason']}")
    pc = r.get("plans_claude")
    if pc:
        L += ["", f"### 5b. Claude-mode plans, judged by Claude ({len(pc['plans'])} scenarios): the primary quality evidence", "",
              "| Query | Destination | Judge | Passed | Revisions | Citations | Budget | Latency (s) |", "|---|---|---|---|---|---|---|---|"]
        L += [f"| {x['query'][:60]}... | {x['destination']} | {x['judge_overall']} | {x['passed']} | {x['revisions']} | "
              f"{x['citation_coverage']} | {x['budget_status']} | {x['latency_s']} |" for x in pc["plans"]]
        L += ["", (f"Summary: mean judge {sum(x['judge_overall'] for x in pc['plans']) / len(pc['plans']):.2f} / 5, "
                f"{sum(x['passed'] for x in pc['plans'])} of {len(pc['plans'])} approved, "
                f"mean citation coverage {sum(x['citation_coverage'] for x in pc['plans']) / len(pc['plans']):.2f}, "
                f"{sum(x['revisions'] for x in pc['plans'])} revisions used. "
                f"Cumulative estimated spend for these plans and DeepEval: ${pc['estimated_spend_usd']} (list-price estimate).")]
    llm_runs = OUT / "LLM_Mode_Runs.md"
    if llm_runs.exists():
        L += ["", "Claude-mode end-to-end runs (judge scores, revision loop, critiques) are recorded in "
              "`eval/results/LLM_Mode_Runs.md`."]
    m = json.loads(get_settings().model_path.with_suffix(".metrics.json").read_text())
    L += ["", "## 6. Suitability model (held-out 20%)", "", "| Model | AUC | Accuracy |", "|---|---|---|",
          f"| Gradient-boosted trees | {m['gbt']['auc']} | {m['gbt']['accuracy']} |",
          f"| Logistic regression baseline | {m['logreg_baseline']['auc']} | {m['logreg_baseline']['accuracy']} |",
          f"| Majority class | - | {m['majority_baseline_accuracy']} |"]
    (OUT / "Evaluation_Report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-deepeval", action="store_true")
    ap.add_argument("--skip-reason", default="--skip-deepeval")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    print("1/5 retrieval ablation...")
    retrieval = eval_retrieval()
    print("2/5 preference classification...")
    prefs = eval_preferences()
    print("3/5 guardrails...")
    guards = eval_guardrails()
    print("4/5 end-to-end plans...")
    plans, states = eval_plans()
    print("5/5 deepeval...")
    deep = {"status": "skipped", "reason": args.skip_reason} if args.skip_deepeval else eval_deepeval(states)
    report = {"llm": get_llm().status(), "retrieval": retrieval, "preferences": prefs, "guardrails": guards,
              "plans": plans, "deepeval": deep}
    (OUT / "latest_results.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    summary = {"retrieval_nDCG@10": {k: v["nDCG@10"] for k, v in retrieval.items()},
               "preference_travel_type_acc": prefs.get("travel_type_accuracy"), "guardrail_block_rate": guards["attack_block_rate"],
               "guardrail_benign_pass": guards["benign_pass_rate"], "plan_mean_judge": plans["mean_judge_score"],
               "plan_pass_rate": plans["pass_rate"], "citation_coverage": plans["mean_citation_coverage"],
               "deepeval": deep.get("metrics", deep.get("reason"))}
    (OUT / "latest_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(report)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
