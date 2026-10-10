# WanderVision - Evaluation Report

Generated: 2026-10-10 14:29 · LLM provider: anthropic

## 1. Retrieval ablation (14 labelled queries, top-10)

| Configuration | P@5 | P@10 | MRR | nDCG@10 | p50 latency (ms) |
|---|---|---|---|---|---|
| keyword (BM25) | 0.643 | 0.643 | 0.786 | 0.762 | 10.1 |
| dense (MiniLM) | 0.514 | 0.521 | 0.705 | 0.727 | 13.6 |
| hybrid (RRF) | 0.629 | 0.586 | 0.854 | 0.861 | 21.5 |
| hybrid + cross-encoder rerank | 0.7 | 0.721 | 0.841 | 0.862 | 575.1 |

## 2. Preference classification (20 labelled queries, classifier: lexicon)

| Metric | Value |
|---|---|
| travel_type_accuracy | 1.0 |
| top_dims_recall | 1.0 |
| days_accuracy | 1.0 |
| budget_accuracy | 1.0 |
| tier_accuracy | 1.0 |
| month_accuracy | 1.0 |
| absent_accuracy | 1.0 |

> Caveat: these cases were written alongside the keyword lexicon, so offline-classifier scores are optimistic. Treat them as a regression suite; unseen phrasings will score lower (the LLM classifier exists to cover them).

## 3. Guardrails red-team

| Metric | Value |
|---|---|
| Attack block rate | 1.0 |
| Block-category accuracy | 1.0 |
| Benign pass rate | 1.0 |
| Benign queries with PII redacted | 2 |

## 4. End-to-end plans, offline rule-based mode (8 scenarios, judge: heuristic): secondary regression suite

> The rule-based judge is lenient by design. The primary quality evidence is the Claude-judged section (5b) and DeepEval (5).

| Metric | Value |
|---|---|
| mean_judge_score | 4.7 |
| pass_rate | 1.0 |
| mean_citation_coverage | 1.0 |
| within_budget_rate | 1.0 |
| preference_coverage | 0.959 |
| latency_ms_p50 | 2408 |
| latency_ms_max | 2739 |

| Query | Destination | Judge | Citations | Budget | Latency (ms) |
|---|---|---|---|---|---|
| A couple wants a 5-day trip focused on beaches, sightseeing and local ... | Bangkok | 4.8 | 1.0 | feasible | 2739 |
| Family of 4 with two kids, limited budget of $2500, 6 days, want highl... | Kerala | 4.8 | 1.0 | feasible | 2365 |
| Solo traveler from Europe, 7 days in October, loves hiking, nature and... | Kerala | 4.4 | 1.0 | unknown | 2506 |
| Group of 4 friends, 5 days of nightlife, beaches and street food in Ma... | Phuket | 4.8 | 1.0 | feasible | 2512 |
| Luxury honeymoon with spa and beaches for 6 days in February, budget 8... | Maldives | 4.8 | 1.0 | feasible | 2450 |
| Retired couple, 8 days of culture, museums and food in Europe in May, ... | Paris | 4.8 | 1.0 | feasible | 1676 |
| Business traveler with 3 free days in Tokyo, wants food and culture... | Tokyo | 4.6 | 1.0 | unknown | 607 |
| 3 friends, adventure and nature, 9 days in January, flying from Oceani... | Cape Town | 4.6 | 1.0 | feasible | 2254 |

## 5. DeepEval (LLM-as-judge)

Judge model: anthropic/claude-opus-5-5 · 6 test cases

| Metric | Mean score | Pass rate |
|---|---|---|
| Recommendation quality [GEval] | 0.567 | 0.5 |
| Answer Relevancy | 0.996 | 1.0 |
| Contextual Relevancy | 0.768 | 1.0 |
| Faithfulness | 1.0 | 1.0 |

### 5b. Claude-mode plans, judged by Claude (6 scenarios): the primary quality evidence

| Query | Destination | Judge | Passed | Revisions | Citations | Budget | Latency (s) |
|---|---|---|---|---|---|---|---|
| A couple wants a 5-day trip focused on beaches, sightseeing ... | Phuket | 3.6 | True | 0 | 0.857 | feasible | 118.1 |
| Family of 4 with two kids, limited budget of $2500, 6 days, ... | Kerala | 3.6 | True | 1 | 1.0 | feasible | 140.2 |
| Luxury honeymoon with spa and beaches for 6 days in February... | Maldives | 3.2 | False | 1 | 1.0 | feasible | 86.9 |
| Solo traveler from Europe, 7 days in October, loves hiking, ... | Kerala | 3.6 | True | 0 | 1.0 | unknown | 89.5 |
| Group of 4 friends, 5 days of nightlife, beaches and street ... | Phuket | 3.8 | True | 0 | 1.0 | feasible | 67.0 |
| Retired couple, 8 days of culture, museums and food in Europ... | Paris | 3.6 | True | 1 | 1.0 | feasible | 67.3 |

Summary: mean judge 3.57 / 5, 5 of 6 approved, mean citation coverage 0.98, 3 revisions used. Cumulative estimated spend for these plans and DeepEval: $2.457 (list-price estimate).

Claude-mode end-to-end runs (judge scores, revision loop, critiques) are recorded in `eval/results/LLM_Mode_Runs.md`.

## 6. Suitability model (held-out 20%)

| Model | AUC | Accuracy |
|---|---|---|
| Gradient-boosted trees | 0.9179 | 0.8477 |
| Logistic regression baseline | 0.9135 | 0.8535 |
| Majority class | - | 0.6999 |
