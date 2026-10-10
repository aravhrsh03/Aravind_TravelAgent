# Claude-mode runs (LLM_PROVIDER=anthropic, claude-opus-5-5), 2026-10-06

These two full multi-agent runs completed with Claude before the API account ran out of credits during the
full evaluation. They were later joined by a larger Claude-judged run on 2026-10-10 (six scenarios, plus DeepEval with Claude as
the examiner): see sections 5 and 5b of `Evaluation_Report.md`, where the mean Claude judge score is 3.57 / 5 and 5 of 6 plans are approved.

## Run 1: "A couple wants a 5-day trip focused on beaches, sightseeing and local food in December, budget $3000, flying from India"

| Step | Engine | Time | Output |
|---|---|---|---|
| Guardrail | deterministic | 5 ms | Input accepted |
| PreferenceClassifier | **Claude** | 5.6 s | Mid couple · Beach + Culture + Foodie (DNA beach 0.9, culture 0.8, food 0.8, nightlife 0.2) |
| Retriever | deterministic | 23.8 s* | 12 trips |
| Recommender | deterministic | 2.5 s | Top pick: Phuket |
| FeasibilityAnalyst | deterministic | 0 ms | budget feasible, duration good |
| ItineraryPlanner | **Claude** | 24.0 s | 5-day Phuket itinerary |
| Critic | **Claude** | 10.5 s | **3.4/5 → revise** |
| FeasibilityAnalyst → ItineraryPlanner → Critic | | 55 s | revised plan, **4.0/5 → pass** |

\* includes one-time model loading. A running server warms models at startup.

**Revised itinerary** "Phuket for Two: 5 Days of Beaches, Temples and Thai Food (December, Mid-Range)":
Day 1 Kata check-in + Thai massage on Kata beach [R00906, R01967] + sunset seafood dinner · Day 2 Phang Nga Bay
sea-kayaking [R00409, R01912] · Day 3 Thai cooking class [R00099, R01079] + Kata Noi beach afternoon · Day 4 Big
Buddha & Wat Chalong [R00099, R01079], Nai Harn swim, Old Phuket Town Sunday walking market [R01206, R03773] ·
Day 5 final swim + airport transfer. Citation coverage 100%, 0 invented citations.

**Judge (Claude) findings on the revised plan:** activity cost totals not reconciled with the tips; extras (transfers,
dinners) costed at $0; dependency on the Sunday market; free beach items without review evidence; flight estimate
optimistic for December; missing rip-current and heat safety notes.
→ *Fix applied:* the planner now returns `est_cost_usd` for extra items, which flows into the cost analysis (ordinary
meals and local transport are excluded because the daily budget already covers them).

## Run 2: "Family of 4 with two kids, limited budget of $2500, 6 days, want highly rated activities and kid-friendly places"

| Step | Engine | Time | Output |
|---|---|---|---|
| PreferenceClassifier | **Claude** | 5.5 s | Budget family · Family-fun (family 1.0, nightlife 0.0) |
| Recommender | deterministic | 2.7 s | Top pick: Kerala |
| ItineraryPlanner | **Claude** | 15.1 s | 6-day Kochi → Munnar → Periyar → Alleppey loop |
| Critic | **Claude** | 11.7 s | **3.4/5 → revise** |
| Revision | | 27 s | **3.6/5 → pass** |
| Total | | 91 s | 5 LLM calls, 0 failures |

**Judge (Claude) findings:** three long drives in four days are too much for young kids; per-person versus per-group
costs are mixed; flights for 4 not budgeted (origin unknown); the houseboat item lost its catalog link after the LLM
renamed it.
→ *Fixes applied:* the prompt now counts drives and transfers against the daily pace and prefers 1-2 bases;
fuzzy matching maps renamed activities back to catalog items and prices.

## DeepEval smoke test (Claude as judge)

On a single toy test case (not the evaluation set): FaithfulnessMetric 1.0, AnswerRelevancyMetric 1.0. This confirmed
the `eval/deepeval_claude.py` bridge works. The full 8-scenario DeepEval run was interrupted by the credit limit.

## Takeaways

- The Claude judge is far stricter than the rule-based judge (3.4-4.0 vs 4.7-4.8). Its critiques were specific
  enough to drive two real fixes.
- The revision loop worked as designed in both runs: a rejected first draft, then an approved revision.
- Claude-mode latency is about 60-90 s per plan with one revision (offline: ~3 s). Itinerary effort was lowered from
  medium to low and tips are capped at 5 to reduce it.
