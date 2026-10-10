"""Renders architecture/Architecture_Diagram.pdf and .jpg."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "architecture"
C = {"data": "#e3f2fd", "rag": "#e8f5e9", "agent": "#fff3e0", "api": "#f3e5f5", "ml": "#fce4ec", "edge": "#37474f"}

fig, ax = plt.subplots(figsize=(17, 10.5))
ax.set_xlim(0, 170)
ax.set_ylim(0, 105)
ax.axis("off")


def box(x, y, w, h, title, lines, color, fs=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.6", fc=color, ec=C["edge"], lw=1.1))
    ax.text(x + w / 2, y + h - 2.3, title, ha="center", va="top", fontsize=fs + 1.5, fontweight="bold", color="#263238")
    ax.text(x + w / 2, y + h - 6.3, "\n".join(lines), ha="center", va="top", fontsize=fs, color="#37474f", linespacing=1.35)


def arrow(x1, y1, x2, y2, label="", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14, lw=1.3, color=C["edge"],
                                 connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 1.5, label, ha="center", fontsize=8, color="#546e7a", style="italic")


def lane(y, h, label):
    ax.add_patch(FancyBboxPatch((1, y), 168, h, boxstyle="round,pad=0.2,rounding_size=2", fc="#fafafa", ec="#cfd8dc", lw=0.8))
    ax.text(3, y + h - 2, label, fontsize=10, fontweight="bold", color="#78909c", va="top")


ax.text(85, 103, "WanderVision - AI Travel Planning & Itinerary Assistant: Architecture", ha="center", fontsize=16,
        fontweight="bold", color="#1a237e")

# Lane 1: offline ingestion
lane(72, 27, "OFFLINE PIPELINE  (scripts/setup_all.py)")
box(4, 75, 22, 19, "Dataset", ["UCI #485 Google travel", "ratings (5,456 users)", "UCI #484 TripAdvisor", "(980 users)",
                               "+ destination catalog"], C["data"])
box(31, 75, 24, 19, "Preprocessing", ["category -> 8-dim", "Traveler DNA", "trip simulation +", "review composition",
                                      "clean / dedupe / validate"], C["data"])
box(60, 75, 22, 19, "Chunking", ["1 review = 1 chunk", "+ structured header", "(dest, type, days, tier,", "month, activities)",
                                 "long text: sentence window"], C["rag"])
box(87, 75, 24, 19, "Embeddings", ["all-MiniLM-L6-v2", "384-d, normalized", "local CPU, no API cost"], C["rag"])
box(116, 75, 24, 19, "Vector DB + Keyword", ["ChromaDB (cosine HNSW)", "+ metadata", "BM25 index (rank-bm25)", "7,712 chunks"], C["rag"])
box(145, 75, 22, 19, "ML training", ["Gradient-boosted", "suitability model", "AUC 0.92 held-out"], C["ml"])
for x1, x2 in ((26, 31), (55, 60), (82, 87), (111, 116)):
    arrow(x1 + 0.4, 84.5, x2 - 0.4, 84.5)
arrow(140.4, 84.5, 144.6, 84.5)

# Lane 2: online RAG + agents
lane(30, 39, "ONLINE: MULTI-AGENT RAG PIPELINE  (blackboard state + agent messages)")
agents = [("1 Guardrail", ["injection / harmful /", "off-topic blocking", "PII redaction"]),
          ("2 Preference\nClassifier", ["Traveler DNA scoring", "trip type, budget,", "days, month, origin"]),
          ("3 Retriever", ["hybrid: dense + BM25", "RRF fusion, rerank", "metadata filters +", "auto-relaxation"]),
          ("4 Recommender", ["5-signal priority:", "evidence, preference,", "suitability (ML),", "feasibility, feedback"]),
          ("5 Feasibility\nAnalyst", ["budget & duration", "tier downgrade /", "swap / shorten"]),
          ("6 Itinerary\nPlanner", ["day-by-day plan", "review citations", "pace & slots"]),
          ("7 Critic\n(LLM-as-judge)", ["5-point rubric", "+ hard fact checks", "pass / revise"])]
w, gap, x0 = 21, 2.5, 4
for i, (t, l) in enumerate(agents):
    x = x0 + i * (w + gap)
    box(x, 44, w, 20, t, l, C["agent"], fs=8.3)
    if i:
        arrow(x - gap + 0.3, 54, x - 0.3, 54)
arrow(x0 + 6 * (w + gap) + w / 2, 64.4, x0 + 4 * (w + gap) + w / 2, 64.4, rad=0.45)
ax.text(x0 + 5 * (w + gap) + w / 2, 66.3, "revise with critic feedback (max 1)", ha="center", fontsize=8, color="#546e7a", style="italic")
box(40, 31, 44, 11, "LLM gateway: Claude (claude-opus-5-5)", ["structured JSON outputs · refusal fallback", "deterministic offline mode when no key"],
    C["ml"], fs=8)
box(90, 31, 42, 11, "Insight services", ["Travel Twins · Destination Duel", "review summaries · Bayesian ratings"], C["ml"], fs=8)
box(138, 31, 29, 11, "Feedback store (SQLite)", ["ranking boosts", "learned experiences"], C["ml"], fs=8)
arrow(128, 74.6, 70, 64.4, "retrieve", rad=0.05)

# Lane 3: serving
lane(2, 25, "SERVING")
box(8, 6, 60, 17, "FastAPI microservice  (uvicorn src.main:app)",
    ["/search  /classify  /recommend  /plan", "/feasibility  /suitability  /compare  /twins",
     "/feedback  /destinations  /experiences  /metrics  /health"], C["api"])
box(80, 6, 50, 17, "Streamlit UI  (streamlit run frontend.py)",
    ["Plan · Search · Twins", "Budget check · Insights", "agent trace, citations, judge scores"], C["api"])
box(140, 6, 27, 17, "Evaluation", ["retrieval ablation", "DeepEval + Claude judge", "guardrail red-team", "pytest (46 tests)"], C["ml"], fs=8)
arrow(68.4, 14.5, 79.6, 14.5, "JSON / REST")
arrow(30, 43.5, 30, 23.4)
ax.text(29, 33, "agent outputs", ha="right", fontsize=8, color="#546e7a", style="italic")
arrow(130.4, 14.5, 139.6, 14.5)
arrow(126, 23.4, 150, 30.6)
ax.text(146, 25.5, "user feedback", fontsize=8, color="#546e7a", style="italic")

for ext in ("pdf", "jpg"):
    fig.savefig(OUT / f"Architecture_Diagram.{ext}", dpi=160, bbox_inches="tight", facecolor="white")
print("written", OUT)
