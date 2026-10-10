# WanderVision API Documentation

Base URL: `http://127.0.0.1:8000` · Interactive Swagger UI: `http://127.0.0.1:8000/docs` · OpenAPI schema: `http://127.0.0.1:8000/openapi.json`

All request bodies are JSON and validated by Pydantic (invalid input → **422**). Requests blocked by guardrails return **400** with `{"detail": {"error": "blocked", "category": "injection|harmful|off_topic|empty|too_long|invalid_parameters", "reasons": [...]}}`. Unknown destinations/ids → **404**. Unexpected errors → **500** `{"error": "internal_error"}`.

Samples below were captured from a live server (offline LLM mode) and shortened (`... N more`).

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Service health |
| `/api/v1/search` | POST | Hybrid (BM25 + dense, RRF, cross-encoder) search over historical trips with metadata filters, personalized prioritization and per-destination review summaries |
| `/api/v1/classify` | POST | Travel preference classification agent |
| `/api/v1/recommend` | POST | Prioritized destinations (5-signal priority) with reasons, suitability, feasibility and top activities with review evidence; includes agent trace |
| `/api/v1/plan` | POST | Full multi-agent plan |
| `/api/v1/feasibility` | POST | Budget and duration feasibility with cost breakdown, cost by tier, max affordable days and notes |
| `/api/v1/suitability` | POST | Itinerary suitability prediction P(rating >= 4) with counterfactual factor explanations |
| `/api/v1/compare` | POST | Destination comparison |
| `/api/v1/twins` | POST | Travel Twins |
| `/api/v1/feedback` | POST | Feedback loop |
| `/api/v1/feedback/stats` | GET | Feedback totals, helpful rate, per-destination learned boosts |
| `/api/v1/destinations` | GET | All destinations with review counts, ratings, costs, seasons, strengths |
| `/api/v1/destinations/Kyoto` | GET | One destination with review summary (praised / panned / complaints) |
| `/api/v1/experiences/R00099` | GET | One historical experience by review id (citation lookup) |
| `/api/v1/metrics` | GET | Per-endpoint request counts, latency, judge scores; LLM usage |

---
## GET `/health`

Service health: document/vector counts, models, LLM provider status.

**Request format:** -

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl http://127.0.0.1:8000/health
```

**Sample response**
```json
{
  "status": "ok",
  "documents": 7712,
  "vectors": 7713,
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2",
  "llm": {
    "provider": "offline",
    "model": null,
    "calls": 0,
    "failures": 0,
    "last_error": null,
    "input_tokens": 0,
    "output_tokens": 0,
    "est_cost_usd": 0.0
  }
}
```

---
## POST `/api/v1/search`

Hybrid (BM25 + dense, RRF, cross-encoder) search over historical trips with metadata filters, personalized prioritization and per-destination review summaries.

**Request format:** `query` (3-2000 chars, required) · `filters` {destinations, travel_types, budget_tiers, regions, categories, min_rating 1-5, max_spend_per_day, months [1-12], min_days, max_days} · `top_k` 1-50 · `mode` hybrid|dense|keyword · `personalize` bool · `params` (see /plan)

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/search -H "Content-Type: application/json" -d '{"query": "5-day trip focused on beaches, sightseeing and local food", "filters": {"min_rating": 4, "travel_types": ["couple"]}, "top_k": 3, "mode": "hybrid"}'
```

**Sample response**
```json
{
  "request_id": "8e8b340b1ac3",
  "query": "5-day trip focused on beaches, sightseeing and local food",
  "guardrail": {
    "allowed": true,
    "sanitized_query": "5-day trip focused on beaches, sightseeing and local food",
    "reasons": [],
    "redactions": [],
    "warnings": [],
    "category": "ok"
  },
  "traveler_dna": {
    "beach": 0.65,
    "culture": 0.65,
    "food": 1.0,
    "nightlife": 0.2,
    "nature": 0.2,
    "shopping": 0.2,
    "wellness": 0.2,
    "family": 0.2
  },
  "segment": "Mid solo · Foodie + Beach + Culture",
  "filters_applied": {
    "travel_types": [
      "couple"
    ],
    "min_rating": 4
  },
  "mode": "hybrid",
  "results": [
    {
      "review_id": "R06582",
      "text": "Cancun, Mexico | couple trip | 5 days | budget-tier budget | Dec | focus: beach | activities: Tacos al pastor street-food tour | Cenote swimming\nUnforgettable!. 5-day trip to Cancun with my partner. Tacos al pastor stree...",
      "user_id": "T48",
      "destination": "Cancun",
      "country": "Mexico",
      "region": "Latin America",
      "category": "beach",
      "rating": 5,
      "travel_type": "couple",
      "visit_month": 12,
      "duration_days": 5,
      "budget_tier": "budget",
      "spend_per_day_usd": 47.21,
      "visit_date": "2021-12-23",
      "source_dataset": "uci484_tripadvisor",
      "scores": {
        "dense": 0.0,
        "bm25": 9.5631,
        "rrf": 0.0152,
        "relevance": 1.0,
        "rating": 1.0,
        "preference_fit": 0.7329,
        "feedback": 0.5,
        "priority": 0.8966
      }
    },
    {
      "review_id": "R00801",
      "text": "Barcelona, Spain | couple trip | 5 days | luxury-tier budget | May | focus: food | activities: La Boqueria and tapas crawl | Barceloneta beach afternoon | Sagrada Familia | Montjuic cable car and magic fountain\nLovely ho...",
      "user_id": "G665",
      "destination": "Barcelona",
      "country": "Spain",
      "region": "Europe",
      "category": "food",
      "rating": 4,
      "travel_type": "couple",
      "visit_month": 5,
      "duration_days": 5,
      "budget_tier": "luxury",
      "spend_per_day_usd": 426.3,
      "visit_date": "2022-05-14",
      "source_dataset": "uci485_google",
      "scores": {
        "dense": 0.0,
        "bm25": 8.2761,
        "rrf": 0.0141,
        "relevance": 0.9537,
        "rating": 0.75,
        "preference_fit": 0.8426,
        "feedback": 0.5,
        "priority": 0.8352
      }
    },
    "... 1 more"
  ],
  "destination_summaries": [
    {
      "destination": "Cancun",
      "matches": 2,
      "avg_rating": 4.5,
      "best_priority": 0.897,
      "praised_activities": [
        {
          "activity": "Tacos al pastor street-food tour",
          "mentions": 1
        },
        {
          "activity": "Cenote swimming",
          "mentions": 1
        },
        "... 1 more"
      ],
      "panned_activities": [
        {
          "activity": "Cenote swimming",
          "mentions": 1
        }
      ],
      "common_complaints": [
        {
          "issue": "crowds / tourist traps",
          "mentions": 1
        },
        {
          "issue": "high costs",
          "mentions": 1
        }
      ]
    },
    {
      "destination": "Barcelona",
      "matches": 1,
      "avg_rating": 4.0,
      "best_priority": 0.835,
      "praised_activities": [
        {
          "activity": "La Boqueria and tapas crawl",
          "mentions": 1
        },
        {
          "activity": "Barceloneta beach afternoon",
          "mentions": 1
        },
        "... 1 more"
      ],
      "panned_activities": [],
      "common_complaints": []
    }
  ],
  "latency_ms": 913.7
}
```

---
## POST `/api/v1/classify`

Travel preference classification agent: Traveler DNA scores, segment, trip type, budget, days, month, origin, intent.

**Request format:** `query` · optional `params`

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/classify -H "Content-Type: application/json" -d '{"query": "Family of 4 with two kids, limited budget of $2500, 6 days, kid-friendly"}'
```

**Sample response**
```json
{
  "request_id": "e8f7ff2de9cf",
  "profile": {
    "dna": {
      "beach": 0.2,
      "culture": 0.2,
      "food": 0.2,
      "nightlife": 0.2,
      "nature": 0.2,
      "shopping": 0.2,
      "wellness": 0.2,
      "family": 1.0
    },
    "top_preferences": [
      "family"
    ],
    "segment": "Budget family · Family-fun",
    "travel_type": "family",
    "budget_tier": "budget",
    "budget_usd": 2500.0,
    "days": 6,
    "travelers": 4,
    "month": null,
    "origin_region": null,
    "destinations": [],
    "regions": [],
    "intent": "plan",
    "must_haves": [],
    "avoid": [],
    "evidence": {
      "family": [
        "family",
        "kids",
        "... 2 more"
      ]
    },
    "classifier_note": "lexicon",
    "defaults_used": [
      "month",
      "origin"
    ]
  },
  "guardrail": {
    "allowed": true,
    "sanitized_query": "Family of 4 with two kids, limited budget of $2500, 6 days, kid-friendly",
    "reasons": [],
    "redactions": [],
    "warnings": [],
    "category": "ok"
  },
  "trace": [
    {
      "agent": "Guardrail",
      "role": "Validates input, blocks prompt injection / harmful / off-topic requests, redacts PII",
      "summary": "Input accepted",
      "duration_ms": 4.1,
      "engine": "deterministic",
      "details": {
        "allowed": true,
        "sanitized_query": "Family of 4 with two kids, limited budget of $2500, 6 days, kid-friendly",
        "reasons": [],
        "redactions": [],
        "warnings": [],
        "category": "ok"
      }
    },
    {
      "agent": "PreferenceClassifier",
      "role": "Classifies travel style, trip type and constraints; scores the Traveler DNA",
      "summary": "Budget family · Family-fun",
      "duration_ms": 40.2,
      "engine": "deterministic",
      "details": {
        "dna": {
          "beach": 0.2,
          "culture": 0.2,
          "food": 0.2,
          "nightlife": 0.2,
          "nature": 0.2,
          "shopping": 0.2,
          "wellness": 0.2,
          "family": 1.0
        },
        "top_preferences": [
          "family"
        ],
        "segment": "Budget family · Family-fun",
        "travel_type": "family",
        "budget_tier": "budget",
        "budget_usd": 2500.0,
        "days": 6,
        "travelers": 4,
        "month": null,
        "origin_region": null,
        "destinations": [],
        "regions": [],
        "intent": "plan",
        "must_haves": [],
        "avoid": [],
        "evidence": {
          "family": [
            "family",
            "kids",
            "... 2 more"
          ]
        },
        "classifier_note": "lexicon",
        "defaults_used": [
          "month",
          "origin"
        ]
      }
    }
  ],
  "latency_ms": 44.4
}
```

---
## POST `/api/v1/recommend`

Prioritized destinations (5-signal priority) with reasons, suitability, feasibility and top activities with review evidence; includes agent trace.

**Request format:** `query` · optional `params`

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/recommend -H "Content-Type: application/json" -d '{"query": "Solo traveler, budget-friendly, hiking and history, 7 days in October from Europe"}'
```

**Sample response**
```json
{
  "request_id": "d07e1ad91de2",
  "profile": {
    "dna": {
      "beach": 0.2,
      "culture": 0.65,
      "food": 0.2,
      "nightlife": 0.2,
      "nature": 0.65,
      "shopping": 0.2,
      "wellness": 0.2,
      "family": 0.2
    },
    "top_preferences": [
      "culture",
      "nature"
    ],
    "segment": "Budget solo · Culture + Nature & Adventure",
    "travel_type": "solo",
    "budget_tier": "budget",
    "budget_usd": null,
    "days": 7,
    "travelers": 1,
    "month": 10,
    "origin_region": "Europe",
    "destinations": [],
    "regions": [],
    "intent": "plan",
    "must_haves": [],
    "avoid": [],
    "evidence": {
      "culture": [
        "history"
      ],
      "nature": [
        "hiking"
      ]
    },
    "classifier_note": "lexicon",
    "defaults_used": [
      "budget"
    ]
  },
  "recommendations": [
    {
      "destination": "Kerala",
      "country": "India",
      "region": "South Asia",
      "summary": "God's Own Country: backwater houseboats, tea hills, Ayurveda and Malabar cuisine.",
      "priority": 0.8136,
      "signals": {
        "evidence": 0.753,
        "preference": 0.775,
        "suitability": 0.986,
        "feasibility": 0.9,
        "feedback": 0.5
      },
      "evidence_rating": 4.01,
      "retrieved_trips": 1,
      "twin_reviews": 19,
      "suitability": {
        "destination": "Kerala",
        "probability": 0.986,
        "label": "excellent fit",
        "factors": [
          {
            "factor": "preference fit",
            "impact": 0.042,
            "direction": "helps"
          },
          {
            "factor": "budget vs destination cost",
            "impact": 0.007,
            "direction": "neutral"
          },
          "... 2 more"
        ]
      },
      "feasibility": {
        "destination": "Kerala",
        "estimate": {
          "tier": "budget",
          "stay_food_local": 175,
          "activities": 158,
          "flights": 750,
          "flights_included": true,
          "contingency": 108,
          "total": 1191
        },
        "cost_by_tier": {
          "budget": 1191,
          "mid": 1537,
          "luxury": 2923
        },
        "budget_usd": null,
        "budget_utilization": null,
        "budget_status": "unknown",
        "recommended_tier": "budget",
        "max_affordable_days": null,
        "duration_status": "good",
        "in_season": true,
        "feasibility_score": 0.9,
        "notes": [
          "No budget given - estimate shown for reference."
        ]
      },
      "reasons": [
        "19 travelers with a similar profile rated it 4.0/5 (adjusted for review count)",
        "Strong match for culture, nature",
        "... 1 more"
      ],
      "rank": 1,
      "label": "Top pick",
      "activities": [
        {
          "activity": "Alleppey backwater houseboat night",
          "dimension": "nature",
          "cost_usd": 90.0,
          "hours": 20.0,
          "score": 0.673,
          "evidence": [
            "R07306",
            "R02064"
          ]
        },
        {
          "activity": "Munnar tea plantations",
          "dimension": "nature",
          "cost_usd": 15.0,
          "hours": 6.0,
          "score": 0.673,
          "evidence": [
            "R01013",
            "R02047"
          ]
        },
        "... 4 more"
      ]
    },
    {
      "destination": "Hanoi",
      "country": "Vietnam",
      "region": "Southeast Asia",
      "summary": "Old Quarter street food capital and launchpad for Ha Long Bay's limestone karsts.",
      "priority": 0.8081,
      "signals": {
        "evidence": 0.736,
        "preference": 0.768,
        "suitability": 0.988,
        "feasibility": 0.9,
        "feedback": 0.5
      },
      "evidence_rating": 3.95,
      "retrieved_trips": 1,
      "twin_reviews": 10,
      "suitability": {
        "destination": "Hanoi",
        "probability": 0.988,
        "label": "excellent fit",
        "factors": [
          {
            "factor": "preference fit",
            "impact": 0.11,
            "direction": "helps"
          },
          {
            "factor": "budget vs destination cost",
            "impact": 0.006,
            "direction": "neutral"
          },
          "... 2 more"
        ]
      },
      "feasibility": {
        "destination": "Hanoi",
        "estimate": {
          "tier": "budget",
          "stay_food_local": 175,
          "activities": 158,
          "flights": 900,
          "flights_included": true,
          "contingency": 123,
          "total": 1356
        },
        "cost_by_tier": {
          "budget": 1356,
          "mid": 1664,
          "luxury": 2857
        },
        "budget_usd": null,
        "budget_utilization": null,
        "budget_status": "unknown",
        "recommended_tier": "budget",
        "max_affordable_days": null,
        "duration_status": "good",
        "in_season": true,
        "feasibility_score": 0.9,
        "notes": [
          "No budget given - estimate shown for reference."
        ]
      },
      "reasons": [
        "10 travelers with a similar profile rated it 4.0/5 (adjusted for review count)",
        "Strong match for culture, nature",
        "... 1 more"
      ],
      "rank": 2,
      "label": "Strong alternative",
      "activities": [
        {
          "activity": "Ha Long Bay overnight cruise",
          "dimension": "nature",
          "cost_usd": 150.0,
          "hours": 24.0,
          "score": 0.673,
          "evidence": [
            "R03258",
            "R05383"
          ]
        },
        {
          "activity": "Hoan Kiem Lake and Temple of Literature",
          "dimension": "culture",
          "cost_usd": 3.0,
          "hours": 3.0,
          "score": 0.673,
          "evidence": [
            "R05981",
            "R02194"
          ]
        },
        "... 4 more"
      ]
    },
    "... 3 more"
  ],
  "retrieval": {
    "filters": {
      "travel_types": [
        "so
```

---
## POST `/api/v1/plan`

Full multi-agent plan: recommendations, feasibility decision, day-by-day itinerary with citations, cost analysis, LLM-as-judge verdict, agent trace and messages.

**Request format:** `query` · `params` {days 1-60, budget_usd, travelers 1-30, travel_type, budget_tier, month 1-12, origin_region, destinations[], regions[], dna{dimension: 0-1}} - all optional overrides

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/plan -H "Content-Type: application/json" -d '{"query": "A couple wants a 5-day trip focused on beaches, sightseeing and local food in December, budget $3000, flying from India", "params": {}}'
```

**Sample response**
```json
{
  "request_id": "f24e245b7e1c",
  "profile": {
    "dna": {
      "beach": 0.65,
      "culture": 0.65,
      "food": 1.0,
      "nightlife": 0.2,
      "nature": 0.2,
      "shopping": 0.2,
      "wellness": 0.2,
      "family": 0.2
    },
    "top_preferences": [
      "food",
      "beach",
      "... 1 more"
    ],
    "segment": "Mid couple · Foodie + Beach + Culture",
    "travel_type": "couple",
    "budget_tier": "mid",
    "budget_usd": 3000.0,
    "days": 5,
    "travelers": 2,
    "month": 12,
    "origin_region": "South Asia",
    "destinations": [],
    "regions": [],
    "intent": "plan",
    "must_haves": [],
    "avoid": [],
    "evidence": {
      "beach": [
        "beaches"
      ],
      "culture": [
        "sightseeing"
      ],
      "food": [
        "food",
        "local food"
      ]
    },
    "classifier_note": "lexicon",
    "defaults_used": []
  },
  "guardrail": {
    "allowed": true,
    "sanitized_query": "A couple wants a 5-day trip focused on beaches, sightseeing and local food in December, budget $3000, flying from India",
    "reasons": [],
    "redactions": [],
    "warnings": [],
    "category": "ok"
  },
  "recommendations": [
    {
      "destination": "Bangkok",
      "country": "Thailand",
      "region": "Southeast Asia",
      "summary": "Electric capital of golden temples, legendary street food, rooftop bars and giant markets.",
      "priority": 0.8147,
      "signals": {
        "evidence": 0.75,
        "preference": 0.722,
        "suitability": 0.986,
        "feasibility": 1.0,
        "feedback": 0.5
      },
      "evidence_rating": 4.0,
      "retrieved_trips": 0,
      "twin_reviews": 3,
      "suitability": {
        "destination": "Bangkok",
        "probability": 0.986,
        "label": "excellent fit",
        "factors": [
          {
            "factor": "preference fit",
            "impact": 0.099,
            "direction": "helps"
          },
          {
            "factor": "season",
            "impact": 0.0,
            "direction": "neutral"
          },
          "... 2 more"
        ]
      },
      "feasibility": {
        "destination": "Bangkok",
        "estimate": {
          "tier": "mid",
          "stay_food_local": 800,
          "activities": 300,
          "flights": 700,
          "flights_included": true,
          "contingency": 180,
          "total": 1980
        },
        "cost_by_tier": {
          "budget": 1430,
          "mid": 1980,
          "luxury": 4180
        },
        "budget_usd": 3000.0,
        "budget_utilization": 0.66,
        "budget_status": "feasible",
        "recommended_tier": "mid",
        "max_affordable_days": 9,
        "duration_status": "good",
        "in_season": true,
        "feasibility_score": 1.0,
        "notes": [
          "Comfortably within budget (≈66% used)."
        ]
      },
      "reasons": [
        "3 travelers with a similar profile rated it 4.0/5 (adjusted for review count)",
        "Strong match for food, beach, culture",
        "... 2 more"
      ],
      "rank": 1,
      "label": "Top pick",
      "activities": [
        {
          "activity": "Yaowarat Chinatown street-food night",
          "dimension": "food",
          "cost_usd": 15.0,
          "hours": 3.0,
          "score": 0.9,
          "evidence": [
            "R00426",
            "R00666"
          ]
        },
        {
          "activity": "Damnoen Saduak floating market",
          "dimension": "food",
          "cost_usd": 30.0,
          "hours": 6.0,
          "score": 0.9,
          "evidence": [
            "R00666",
            "R02878"
          ]
        },
        "... 4 more"
      ]
    },
    {
      "destination": "Goa",
      "country": "India",
      "region": "South Asia",
      "summary": "Laid-back Indian coast of palm-lined beaches, Portuguese churches, seafood shacks and beach parties.",
      "priority": 0.8076,
      "signals": {
        "evidence": 0.724,
        "preference": 0.722,
        "suitability": 0.984,
        "feasibility": 1.0,
        "feedback": 0.5
      },
      "evidence_rating": 3.9,
      "retrieved_trips": 3,
      "twin_reviews": 4,
      "suitability": {
        "destination": "Goa",
        "probability": 0.984,
        "label": "excellent fit",
        "factors": [
          {
            "factor": "preference fit",
            "impact": 0.133,
            "direction": "helps"
          },
          {
            "factor": "season",
            "impact": 0.0,
            "direction": "neutral"
          },
          "... 2 more"
        ]
      },
      "feasibility": {
        "destination": "Goa",
        "estimate": {
          "tier": "mid",
          "stay_food_local": 650,
          "activities": 180,
          "flights": 300,
          "flights_included": true,
          "contingency": 113,
          "total": 1243
        },
        "cost_by_tier": {
          "budget": 803,
          "mid": 1243,
          "luxury": 2948
        },
        "budget_usd": 3000.0,
        "budget_utilization": 0.414,
        "budget_status": "feasible",
        "recommended_tier": "luxury",
        "max_affordable_days": 14,
        "duration_status": "good",
        "in_season": true,
        "feasibility_score": 1.0,
        "notes": [
          "Comfortably within budget (≈41% used)."
        ]
      },
      "reasons": [
        "4 travelers with a similar profile rated it 3.9/5 (adjusted for review count)",
        "Strong match for food, beach, culture",
        "... 2 more"
      ],
      "rank": 2,
      "label": "Budget alternative",
      "activities": [
        {
          "activity": "Goan fish thali and xacuti food tour",
          "dimension": "food",
          "cost_usd": 15.0,
          "hours": 3.0,
          "score": 0.9,
          "evidence": [
            "R03083",
            "R04191"
          ]
        },
        {
          "activity": "Beach hopping Palolem to Agonda",
          "dimension": "beach",
        
```

---
## POST `/api/v1/feasibility`

Budget and duration feasibility with cost breakdown, cost by tier, max affordable days and notes.

**Request format:** `destination` · `days` · `travelers` · `budget_tier` · optional `budget_usd`, `origin_region`, `month`

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/feasibility -H "Content-Type: application/json" -d '{"destination": "Reykjavik", "days": 5, "travelers": 2, "budget_tier": "mid", "budget_usd": 3000, "origin_region": "South Asia", "month": 7}'
```

**Sample response**
```json
{
  "destination": "Reykjavik",
  "estimate": {
    "tier": "mid",
    "stay_food_local": 2600,
    "activities": 1350,
    "flights": 1500,
    "flights_included": true,
    "contingency": 545,
    "total": 5995
  },
  "cost_by_tier": {
    "budget": 4455,
    "mid": 5995,
    "luxury": 9735
  },
  "budget_usd": 3000.0,
  "budget_utilization": 1.998,
  "budget_status": "over_budget",
  "recommended_tier": null,
  "max_affordable_days": 1,
  "duration_status": "good",
  "in_season": true,
  "feasibility_score": 0.5,
  "notes": [
    "Estimated $5,995 exceeds the $3,000 budget by 100%.",
    "Even budget-tier travel does not fit; consider a cheaper destination or fewer days."
  ]
}
```

---
## POST `/api/v1/suitability`

Itinerary suitability prediction P(rating >= 4) with counterfactual factor explanations.

**Request format:** `destination` · `query` or `dna` · `travel_type` · `budget_tier` · `month` · `days`

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/suitability -H "Content-Type: application/json" -d '{"destination": "Goa", "query": "beach party with friends", "travel_type": "friends", "budget_tier": "budget", "month": 7, "days": 4}'
```

**Sample response**
```json
{
  "traveler_dna": {
    "beach": 0.65,
    "culture": 0.2,
    "food": 0.2,
    "nightlife": 0.65,
    "nature": 0.2,
    "shopping": 0.2,
    "wellness": 0.2,
    "family": 0.2
  },
  "destination": "Goa",
  "probability": 0.707,
  "label": "good fit",
  "factors": [
    {
      "factor": "preference fit",
      "impact": 0.438,
      "direction": "helps"
    },
    {
      "factor": "season",
      "impact": -0.284,
      "direction": "hurts"
    },
    "... 2 more"
  ]
}
```

---
## POST `/api/v1/compare`

Destination comparison: Bayesian, similarity-weighted ratings from travelers similar to the query (API only; the web UI has no tab for it).

**Request format:** `destinations` [2] · `query` or `dna` · optional `travel_type`

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/compare -H "Content-Type: application/json" -d '{"destinations": ["Bali", "Phuket"], "query": "beaches and nightlife with friends"}'
```

**Sample response**
```json
{
  "traveler_dna": {
    "beach": 0.65,
    "culture": 0.2,
    "food": 0.2,
    "nightlife": 0.65,
    "nature": 0.2,
    "shopping": 0.2,
    "wellness": 0.2,
    "family": 0.2
  },
  "destinations": {
    "Bali": {
      "similar_travelers": {
        "twin_reviews": 70,
        "weighted_rating": 4.31,
        "bayes_rating": 4.264,
        "pct_4plus": 0.914
      },
      "all_travelers": {
        "reviews": 272,
        "avg_rating": 4.27
      },
      "praised_activities": [
        {
          "activity": "Mount Batur sunrise trek",
          "mentions": 94
        },
        {
          "activity": "Surf lesson at Kuta or Canggu",
          "mentions": 88
        },
        "... 1 more"
      ],
      "panned_activities": [
        {
          "activity": "Ubud art market",
          "mentions": 29
        },
        {
          "activity": "Sunset at Uluwatu Temple with Kecak fire dance",
          "mentions": 21
        },
        "... 1 more"
      ],
      "common_complaints": [
        {
          "issue": "crowds / tourist traps",
          "mentions": 105
        },
        {
          "issue": "off-season weather",
          "mentions": 30
        },
        "... 1 more"
      ]
    },
    "Phuket": {
      "similar_travelers": {
        "twin_reviews": 81,
        "weighted_rating": 4.52,
        "bayes_rating": 4.465,
        "pct_4plus": 0.914
      },
      "all_travelers": {
        "reviews": 282,
        "avg_rating": 4.17
      },
      "praised_activities": [
        {
          "activity": "Elephant sanctuary visit",
          "mentions": 143
        },
        {
          "activity": "Phang Nga Bay sea-kayaking",
          "mentions": 104
        },
        "... 1 more"
      ],
      "panned_activities": [
        {
          "activity": "Big Buddha and Wat Chalong",
          "mentions": 29
        },
        {
          "activity": "Thai massage on Kata beach",
          "mentions": 28
        },
        "... 1 more"
      ],
      "common_complaints": [
        {
          "issue": "crowds / tourist traps",
          "mentions": 140
        },
        {
          "issue": "trip too short",
          "mentions": 44
        },
        "... 1 more"
      ]
    }
  },
  "winner": "Phuket",
  "margin": 0.201,
  "confidence": "medium"
}
```

---
## POST `/api/v1/twins`

Travel Twins: nearest historical travelers by Traveler DNA, their trips, and their favourite destinations.

**Request format:** `query` or `dna` · `k` 1-100

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/twins -H "Content-Type: application/json" -d '{"query": "museums, temples, history and local food", "k": 2}'
```

**Sample response**
```json
{
  "traveler_dna": {
    "beach": 0.2,
    "culture": 1.0,
    "food": 1.0,
    "nightlife": 0.2,
    "nature": 0.2,
    "shopping": 0.2,
    "wellness": 0.2,
    "family": 0.2
  },
  "twins": [
    {
      "user_id": "G2586",
      "similarity": 0.901,
      "source_dataset": "uci485_google",
      "dna": {
        "beach": 0.141,
        "culture": 0.892,
        "food": 0.915,
        "nightlife": 0.27,
        "nature": 0.253,
        "shopping": 0.437,
        "wellness": 0.494,
        "family": 0.42
      },
      "trips": [
        {
          "review_id": "R03081",
          "destination": "Marrakech",
          "rating": 4,
          "travel_type": "solo",
          "title": "Lovely holiday"
        }
      ]
    },
    {
      "user_id": "G2606",
      "similarity": 0.872,
      "source_dataset": "uci485_google",
      "dna": {
        "beach": 0.267,
        "culture": 0.936,
        "food": 0.836,
        "nightlife": 0.134,
        "nature": 0.543,
        "shopping": 0.472,
        "wellness": 0.269,
        "family": 0.378
      },
      "trips": [
        {
          "review_id": "R03104",
          "destination": "Singapore",
          "rating": 5,
          "travel_type": "couple",
          "title": "Absolutely loved it"
        },
        {
          "review_id": "R03103",
          "destination": "Santorini",
          "rating": 4,
          "travel_type": "couple",
          "title": "Great trip"
        }
      ]
    }
  ],
  "twin_favourites": [
    {
      "destination": "Tokyo",
      "twin_reviews": 19,
      "twin_avg_rating": 4.53,
      "weighted_rating": 4.53,
      "bayes_rating": 4.332,
      "pct_4plus": 0.895
    },
    {
      "destination": "London",
      "twin_reviews": 18,
      "twin_avg_rating": 4.44,
      "weighted_rating": 4.47,
      "bayes_rating": 4.288,
      "pct_4plus": 0.944
    },
    "... 6 more"
  ]
}
```

---
## POST `/api/v1/feedback`

Feedback loop: updates the destination ranking boost; positive feedback with 8+ words is guardrail-checked and indexed as a new experience.

**Request format:** `destination` · `rating` 1-5 · optional `request_id`, `helpful`, `comment` (≤1000), `travel_type`

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/feedback -H "Content-Type: application/json" -d '{"destination": "Kyoto", "rating": 5, "helpful": true, "comment": "The temple walk at dawn and the kaiseki dinner were perfect for us as a couple"}'
```

**Sample response**
```json
{
  "feedback_id": 1,
  "new_ranking_boost": 0.167,
  "indexed_as_experience": "F00001"
}
```

---
## GET `/api/v1/feedback/stats`

Feedback totals, helpful rate, per-destination learned boosts.

**Request format:** -

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl http://127.0.0.1:8000/api/v1/feedback/stats
```

**Sample response**
```json
{
  "total_feedback": 1,
  "avg_rating": 5.0,
  "helpful_rate": 1.0,
  "per_destination": [
    {
      "destination": "Kyoto",
      "count": 1,
      "avg_rating": 5.0,
      "ranking_boost": 0.167
    }
  ],
  "recent": [
    {
      "ts": 1791626569.490761,
      "destination": "Kyoto",
      "rating": 5,
      "helpful": 1,
      "comment": "The temple walk at dawn and the kaiseki dinner were perfect for us as a couple"
    }
  ]
}
```

---
## GET `/api/v1/destinations`

All destinations with review counts, ratings, costs, seasons, strengths.

**Request format:** -

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl http://127.0.0.1:8000/api/v1/destinations
```

**Sample response**
```json
[
  {
    "name": "Bali",
    "country": "Indonesia",
    "region": "Southeast Asia",
    "summary": "Volcanic island of rice terraces, surf beaches, Hindu temples and world-class spa retreats.",
    "reviews": 272,
    "avg_rating": 4.27,
    "daily_cost": {
      "budget": 35,
      "mid": 90,
      "luxury": 300
    },
    "best_months": [
      4,
      5,
      "... 5 more"
    ],
    "strengths": {
      "beach": 0.95,
      "culture": 0.7,
      "food": 0.7,
      "nightlife": 0.6,
      "nature": 0.85,
      "shopping": 0.4,
      "wellness": 0.95,
      "family": 0.6
    }
  },
  {
    "name": "Goa",
    "country": "India",
    "region": "South Asia",
    "summary": "Laid-back Indian coast of palm-lined beaches, Portuguese churches, seafood shacks and beach parties.",
    "reviews": 185,
    "avg_rating": 3.71,
    "daily_cost": {
      "budget": 25,
      "mid": 65,
      "luxury": 220
    },
    "best_months": [
      11,
      12,
      "... 3 more"
    ],
    "strengths": {
      "beach": 0.9,
      "culture": 0.55,
      "food": 0.75,
      "nightlife": 0.85,
      "nature": 0.5,
      "shopping": 0.45,
      "wellness": 0.55,
      "family": 0.5
    }
  },
  "... 30 more"
]
```

---
## GET `/api/v1/destinations/Kyoto`

One destination with review summary (praised / panned / complaints).

**Request format:** path: name

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl http://127.0.0.1:8000/api/v1/destinations/Kyoto
```

**Sample response**
```json
{
  "destination": "Kyoto",
  "country": "Japan",
  "region": "East Asia",
  "summary": "Japan's ancient capital: 1,600 temples, geisha districts, zen gardens and kaiseki dining.",
  "reviews": 180,
  "avg_rating": 3.77,
  "bayes_rating": 3.78,
  "by_travel_type": [
    {
      "travel_type": "business",
      "count": 3,
      "mean": 3.67
    },
    {
      "travel_type": "couple",
      "count": 39,
      "mean": 4.0
    },
    "... 3 more"
  ],
  "best_months": [
    3,
    4,
    "... 3 more"
  ],
  "daily_cost": {
    "budget": 70,
    "mid": 160,
    "luxury": 450
  },
  "strengths": {
    "beach": 0.05,
    "culture": 1.0,
    "food": 0.85,
    "nightlife": 0.35,
    "nature": 0.75,
    "shopping": 0.55,
    "wellness": 0.65,
    "family": 0.55
  },
  "ideal_days": 4,
  "praised_activities": [
    {
      "activity": "Arashiyama bamboo grove and Tenryu-ji",
      "mentions": 68
    },
    {
      "activity": "Kinkaku-ji Golden Pavilion",
      "mentions": 63
    },
    "... 2 more"
  ],
  "panned_activities": [
    {
      "activity": "Onsen day at Kurama",
      "mentions": 18
    },
    {
      "activity": "Kinkaku-ji Golden Pavilion",
      "mentions": 18
    },
    "... 2 more"
  ],
  "common_complaints": [
    {
      "issue": "crowds / tourist traps",
      "mentions": 89
    },
    {
      "issue": "not child-friendly",
      "mentions": 45
    },
    "... 2 more"
  ]
}
```

---
## GET `/api/v1/experiences/R00099`

One historical experience by review id (citation lookup).

**Request format:** path: review_id

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl http://127.0.0.1:8000/api/v1/experiences/R00099
```

**Sample response**
```json
{
  "review_id": "R00099",
  "text": "Phuket, Thailand | couple trip | 5 days | budget-tier budget | Mar | focus: family | activities: Big Buddha and Wat Chalong | Thai cooking class | Elephant sanctuary visit\nAbsolutely loved it. Anniversary getaway: 5 days...",
  "user_id": "G88",
  "destination": "Phuket",
  "country": "Thailand",
  "region": "Southeast Asia",
  "category": "family",
  "rating": 5,
  "travel_type": "couple",
  "visit_month": 3,
  "duration_days": 5,
  "budget_tier": "budget",
  "spend_per_day_usd": 27.26,
  "visit_date": "2023-03-27",
  "source_dataset": "uci485_google"
}
```

---
## GET `/api/v1/metrics`

Per-endpoint request counts, latency, judge scores; LLM usage.

**Request format:** -

**Response:** HTTP 200, JSON

**Sample request**
```bash
curl http://127.0.0.1:8000/api/v1/metrics
```

**Sample response**
```json
{
  "endpoints": [
    {
      "endpoint": "classify",
      "requests": 1,
      "avg_latency_ms": 44.4,
      "avg_judge_score": null,
      "blocked": 0
    },
    {
      "endpoint": "plan",
      "requests": 2,
      "avg_latency_ms": 2324.1,
      "avg_judge_score": 4.6,
      "blocked": 0
    },
    "... 2 more"
  ],
  "llm": {
    "provider": "offline",
    "model": null,
    "calls": 0,
    "failures": 0,
    "last_error": null,
    "input_tokens": 0,
    "output_tokens": 0,
    "est_cost_usd": 0.0
  },
  "feedback": 1
}
```

---
## Error example: guardrail block
```json
{
  "detail": {
    "error": "blocked",
    "request_id": "bc527e2ec041",
    "category": "injection",
    "reasons": [
      "Possible prompt-injection attempt detected; request blocked."
    ]
  }
}
```
