"""Builds presentation/Project_Presentation.pptx (16:9) from the latest evaluation results.

    python scripts/build_deck.py
"""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import MSO_ANCHOR  # noqa: E402
from pptx.util import Inches, Pt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation"
RES = json.loads((ROOT / "eval" / "results" / "latest_results.json").read_text(encoding="utf-8"))
MODEL = json.loads((ROOT / "data" / "processed" / "suitability_model.metrics.json").read_text())

# Palette matches the web UI: deep teal, terracotta accent, warm paper and sand.
NAVY, BLUE, ORANGE, GREY, LIGHT = (RGBColor(0x24, 0x54, 0x4F), RGBColor(0x2F, 0x6F, 0x6B), RGBColor(0xB4, 0x49, 0x2A),
                                   RGBColor(0x6E, 0x67, 0x5D), RGBColor(0xF3, 0xEC, 0xE0))
PAPER, INK, EDGE, BLUSH = RGBColor(0xFB, 0xF8, 0xF3), RGBColor(0x2A, 0x27, 0x23), RGBColor(0xD9, 0xCD, 0xB8), RGBColor(0xF4, 0xDC, 0xD3)
HEAD_FONT = "Georgia"
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide(title: str, subtitle: str | None = None):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = PAPER
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(1.05))
    band.fill.solid()
    band.fill.fore_color.rgb = NAVY
    band.line.fill.background()
    tb = s.shapes.add_textbox(Inches(0.5), Inches(0.18), Inches(12.3), Inches(0.7)).text_frame
    tb.text = title
    tb.paragraphs[0].font.name = HEAD_FONT
    tb.paragraphs[0].font.size, tb.paragraphs[0].font.bold = Pt(30), True
    tb.paragraphs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    if subtitle:
        st = s.shapes.add_textbox(Inches(0.5), Inches(1.15), Inches(12.3), Inches(0.5)).text_frame
        st.text = subtitle
        st.paragraphs[0].font.size, st.paragraphs[0].font.italic = Pt(15), True
        st.paragraphs[0].font.color.rgb = GREY
    foot = s.shapes.add_textbox(Inches(0.5), Inches(7.05), Inches(12.3), Inches(0.3)).text_frame
    foot.text = "WanderVision · AI-Powered Travel Planning & Itinerary Assistant"
    foot.paragraphs[0].font.size, foot.paragraphs[0].font.color.rgb = Pt(10), GREY
    return s


def bullets(s, items, x=0.6, y=1.75, w=12.1, h=5.1, size=19):
    tf = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)).text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        sub = it.startswith("  ")
        p.text = ("– " if sub else "• ") + it.strip()
        p.font.size = Pt(size - 3 if sub else size)
        p.font.color.rgb = GREY if sub else INK
        p.level = 1 if sub else 0
        p.space_after = Pt(6)
    return tf


def card(s, x, y, w, h, title, body, color=LIGHT, title_color=NAVY, size=13):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.color.rgb = EDGE
    shp.adjustments[0] = 0.08
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_top = tf.margin_left = tf.margin_right = Inches(0.15)
    tf.text = title
    tf.paragraphs[0].font.size, tf.paragraphs[0].font.bold = Pt(size + 3), True
    tf.paragraphs[0].font.color.rgb = title_color
    for line in body:
        p = tf.add_paragraph()
        p.text = line
        p.font.size, p.font.color.rgb = Pt(size), INK
    return shp


def chart_retrieval(path: Path) -> None:
    r = RES["retrieval"]
    labels = ["BM25", "Dense", "Hybrid\n(RRF)", "Hybrid +\nrerank"]
    keys = list(r)
    fig, ax = plt.subplots(figsize=(6.4, 3.9), dpi=150)
    x = range(len(keys))
    for i, (m, c) in enumerate((("MRR", "#A9CBC7"), ("nDCG@10", "#2F6F6B"), ("P@10", "#B4492A"))):
        vals = [r[k][m] for k in keys]
        bars = ax.bar([j + (i - 1) * 0.26 for j in x], vals, 0.26, label=m, color=c)
        ax.bar_label(bars, fmt="%.2f", fontsize=7)
    ax.set_xticks(list(x), labels)
    ax.set_ylim(0, 1.05)
    ax.legend(ncol=3, fontsize=8, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Retrieval ablation (14 labelled queries)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def chart_deepeval(path: Path) -> bool:
    d = RES["deepeval"]
    if d.get("status") != "ok":
        return False
    names = list(d["metrics"])
    vals = [d["metrics"][n]["mean_score"] for n in names]
    fig, ax = plt.subplots(figsize=(6.4, 3.9), dpi=150)
    bars = ax.barh([n.replace(" [GEval]", "") for n in names], vals, color="#2F6F6B")
    ax.bar_label(bars, fmt="%.2f", fontsize=8)
    ax.set_xlim(0, 1.1)
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"DeepEval mean scores ({d['n']} plans, Claude as judge)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def main() -> None:
    OUT.mkdir(exist_ok=True)
    tmp = OUT / "_charts"
    tmp.mkdir(exist_ok=True)
    plans, guards, prefs = RES["plans"], RES["guardrails"], RES["preferences"]

    # 1 Title
    s = prs.slides.add_slide(BLANK)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()
    tf = s.shapes.add_textbox(Inches(0.9), Inches(2.2), Inches(11.5), Inches(3)).text_frame
    tf.text = "WanderVision"
    tf.paragraphs[0].font.name = HEAD_FONT
    tf.paragraphs[0].font.size, tf.paragraphs[0].font.bold = Pt(54), True
    tf.paragraphs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    for txt, size, col in (("AI-Powered Travel Planning & Itinerary Assistant", 28, RGBColor(0xF3, 0xEC, 0xE0)),
                           ("Hybrid RAG · Seven specialist agents · Suitability ML · LLM-as-judge · Feedback loop", 18, ORANGE),
                           ("Capstone Project 2 · Prodapt PU Bootcamp · <Participant name>", 16, RGBColor(0xD9, 0xCD, 0xB8))):
        p = tf.add_paragraph()
        p.text, p.font.size, p.font.color.rgb = txt, Pt(size), col
        p.space_before = Pt(10)

    # 2 Problem statement
    s = slide("Problem Statement")
    bullets(s, ["Travel platforms hold thousands of reviews, ratings and trip records, but agents search them by hand",
                "Recurring questions take tens of minutes each:",
                "  \"A 5-day beach, sightseeing and food trip: what similar trips were rated highly?\"",
                "  \"Travelers like these are choosing between two destinations: which did similar travelers rate better?\"",
                "  \"Limited budget, but they want highly rated activities: what should we recommend?\"",
                "Answers vary between agents, are rarely backed by evidence, and ignore budget and season feasibility"])

    # 3 Business need
    s = slide("Business Need")
    for i, (t, b) in enumerate([("Speed", ["Seconds, not tens of minutes", "per enquiry"]),
                                ("Trust", ["Every recommendation cites", "real historical reviews"]),
                                ("Feasibility", ["Budget, trip length and season", "checked before proposing"]),
                                ("Personalization", ["Match on what similar", "travelers loved, not averages"]),
                                ("Safety", ["Injection, PII and", "unsafe-request guardrails"]),
                                ("Improvement", ["Feedback re-ranks results and", "grows the knowledge base"])]):
        card(s, 0.6 + (i % 3) * 4.1, 1.8 + (i // 3) * 2.55, 3.8, 2.25, t, b, size=19)

    # 4 Solution overview
    s = slide("Solution Overview", "A microservice + UI that turns a natural-language enquiry into an evidence-backed plan")
    feats = [("Traveler DNA", ["8-dimension preference profile", "inferred from free text"]),
             ("Hybrid RAG", ["BM25 + embeddings, RRF fusion,", "cross-encoder, metadata filters"]),
             ("Seven specialist agents", ["Guardrail → … → Critic", "with a revision loop"]),
             ("Suitability ML", [f"P(rating ≥ 4), AUC {MODEL['gbt']['auc']:.2f}", "with factor explanations"]),
             ("Search past trips", ["Filter by destination, trip type,", "rating and spending style"]),
             ("Travel twins", ["Nearest historical travelers", "and their favourite places"]),
             ("Budget check", ["Cost by tier, flights, max days,", "season and length checks"]),
             ("Feedback loop", ["Ranking boosts + guarded", "new experiences"])]
    for i, (t, b) in enumerate(feats):
        card(s, 0.5 + (i % 4) * 3.12, 1.85 + (i // 4) * 2.55, 2.95, 2.3, t, b, size=16)

    # 5 Architecture
    s = slide("Architecture")
    s.shapes.add_picture(str(ROOT / "architecture" / "Architecture_Diagram.jpg"), Inches(1.0), Inches(1.15), height=Inches(5.85))

    # 6 Data flow
    s = slide("Data Flow: from UCI ratings to an answer")
    steps = [("Dataset", ["UCI #485 (5,456 users)", "UCI #484 (980 users)", "category ratings only"]),
             ("Preprocess", ["categories → 8-dim DNA", "simulate trips + reviews", "clean · dedupe · validate"]),
             ("Chunk", ["1 review = 1 chunk", "+ structured header", "7,712 chunks"]),
             ("Embed + Index", ["MiniLM 384-d → ChromaDB", "BM25 keyword index", "metadata for filters"]),
             ("Retrieve", ["dense + BM25 → RRF", "cross-encoder rerank", "priority scoring"]),
             ("Agents → API → UI", ["recommend · plan · judge", "FastAPI endpoints", "Streamlit UI"])]
    for i, (t, b) in enumerate(steps):
        card(s, 0.35 + i * 2.13, 2.0, 1.95, 2.6, t, b, size=14)
        if i:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(0.35 + i * 2.13 - 0.2), Inches(3.15), Inches(0.22), Inches(0.3))
            a.fill.solid()
            a.fill.fore_color.rgb = ORANGE
            a.line.fill.background()
    bullets(s, ["The source data has real traveler preferences but no review text, destinations or dates, so trips are simulated "
                "from each traveler's real preference profile (seed 42, fully documented)",
                "Rating and review text come from one satisfaction model, so text, stars and metadata agree"],
            y=5.0, h=1.8, size=15)

    # 7 Tech stack
    s = slide("Technology Stack")
    stack = [("LLM", "Claude Opus 5.5 (claude-opus-5-5): structured JSON outputs, refusal fallback, offline fallback"),
             ("Embeddings", "sentence-transformers all-MiniLM-L6-v2 (local, 384-d)"),
             ("Reranker", "cross-encoder ms-marco-MiniLM-L-6-v2"),
             ("Vector DB", "ChromaDB 1.0.20 (cosine HNSW + metadata filters) · BM25 (rank-bm25)"),
             ("ML", "scikit-learn HistGradientBoosting (itinerary suitability)"),
             ("Backend / UI", "FastAPI + Pydantic + Uvicorn · Streamlit + Plotly"),
             ("Evaluation", "DeepEval (Claude as judge) · custom retrieval/guardrail suites · pytest"),
             ("Storage", "SQLite (feedback, request log) · CSV corpus · JSON catalog")]
    tbl = s.shapes.add_table(len(stack), 2, Inches(0.7), Inches(1.6), Inches(11.9), Inches(5.0)).table
    tbl.columns[0].width, tbl.columns[1].width = Inches(2.4), Inches(9.5)
    for r, (k, v) in enumerate(stack):
        for c, txt in enumerate((k, v)):
            cell = tbl.cell(r, c)
            cell.text = txt
            cell.text_frame.paragraphs[0].font.size = Pt(16)
            cell.text_frame.paragraphs[0].font.bold = c == 0

    # 8 Agent workflow
    s = slide("Agent Workflow", "Blackboard state + addressed messages · every step timed and shown in the UI")
    agents = [("1 Guardrail", "injection · harmful · off-topic · PII"), ("2 Preference", "Traveler DNA · trip type · budget"),
              ("3 Retriever", "hybrid search · filter relaxation"), ("4 Recommender", "5-signal priority · activities"),
              ("5 Feasibility", "downgrade tier · swap · shorten"), ("6 Itinerary", "day plan · review citations"),
              ("7 Critic", "LLM-as-judge · 5-point rubric")]
    for i, (t, b) in enumerate(agents):
        color = BLUSH if i in (1, 5, 6) else LIGHT
        card(s, 0.22 + i * 1.84, 1.9, 1.8, 1.75, t, [b], color=color, size=12)
    bullets(s, ["Pink cards use Claude (with a deterministic fallback); sand cards are deterministic code (facts, money, ranking)",
                "Critic below 3.5/5 → structured feedback (e.g. must_cover: nature, tier: budget) → Feasibility → Itinerary → "
                "Critic again (max 1 revision)",
                "The Critic's LLM scores are capped by hard checks: citation validity, budget status, day count, preference coverage"],
            y=4.0, h=2.2, size=16)

    # 9 Demo
    s = slide("Demo", "Live: uvicorn src.main:app · streamlit run frontend.py")
    first = plans["plans"][0]
    bullets(s, [f"Query: \"{first['query']}\"",
                f"  Segment: {first['segment'].replace(' · ', ', ')} → top pick {first['destination']}, {first['budget_status']}, "
                f"judge {first['judge_overall']}/5, {first['citation_coverage'] * 100:.0f}% of activities cited",
                "Walkthrough: Plan a trip tab (interest radar, itinerary with past-review popovers, cost breakdown, how-it-was-made trace)",
                "Travel twins tab: a museums and history lover, with the closest past travelers and where they were happiest",
                "Budget check tab: Reykjavik on $3,000 from South Asia → over budget, cost by tier, satisfaction drivers",
                "Guardrails: \"ignore previous instructions…\" → blocked (injection); \"smuggle gold…\" → blocked (harmful)",
                "Feedback: rate a recommendation → ranking boost updates live on the Insights tab"], size=17)

    # 10 Evaluation: retrieval + plans
    s = slide("Evaluation Results (1/2): Retrieval & end-to-end plans")
    chart_retrieval(tmp / "retrieval.png")
    s.shapes.add_picture(str(tmp / "retrieval.png"), Inches(0.4), Inches(1.4), height=Inches(4.3))
    pc = RES.get("plans_claude")
    if pc:
        rows = pc["plans"]
        card(s, 7.7, 1.45, 5.2, 4.9, f"End-to-end with Claude ({len(rows)} scenarios)", [
            f"Claude judge: mean {np.mean([x['judge_overall'] for x in rows]):.1f}/5",
            f"Approved: {sum(x['passed'] for x in rows)} of {len(rows)} (revisions used: {sum(x['revisions'] for x in rows)})",
            f"Citation coverage: {np.mean([x['citation_coverage'] for x in rows]) * 100:.0f}%",
            f"Within budget: {sum(x['budget_status'] in ('feasible', 'tight', 'unknown') for x in rows)} of {len(rows)}",
            f"Time per plan: about {np.mean([x['latency_s'] for x in rows]):.0f}s (loaded laptop)",
            "", "Retrieval: hybrid beats either retriever alone;", "the reranker lifts P@10 at +0.8s CPU",
            "", f"(Rule-based regression suite: {plans['n']} scenarios, {plans['mean_judge_score']}/5)"], size=14)
    else:
        card(s, 7.7, 1.45, 5.2, 4.9, f"End-to-end ({plans['n']} scenarios)", [
            f"Judge ({plans['judge_engine']}): mean {plans['mean_judge_score']}/5",
            f"Pass rate: {plans['pass_rate'] * 100:.0f}%"], size=14)

    # 11 Evaluation: DeepEval, guardrails, model
    s = slide("Evaluation Results (2/2): LLM quality, safety, ML")
    if chart_deepeval(tmp / "deepeval.png"):
        s.shapes.add_picture(str(tmp / "deepeval.png"), Inches(0.4), Inches(1.4), height=Inches(4.3))
    else:
        card(s, 0.5, 1.45, 6.9, 4.9, "Claude mode: LLM-as-judge in action", [
            "Couple · beaches, food · Dec · $3,000 → Phuket",
            "   Critic 3.4/5 → revise → 4.0/5 approved",
            "Family of 4 · $2,500 · 6 days → Kerala",
            "   Critic 3.4/5 → revise → 3.6/5 approved",
            "", "Critiques that drove fixes:",
            "• extras costed at $0 → est_cost_usd added",
            "• 3 long drives in 4 days for kids → pace rule",
            "• renamed activity lost its price → fuzzy match",
            "", "DeepEval bridge verified (faithfulness 1.0,", "relevancy 1.0 on a smoke test); full DeepEval run still to be executed"],
            size=14)
    card(s, 7.7, 1.45, 5.2, 2.55, "Guardrails red-team", [
        f"Attacks blocked: {guards['attack_block_rate'] * 100:.0f}% (category acc. {guards['category_accuracy'] * 100:.0f}%)",
        f"Benign allowed: {guards['benign_pass_rate'] * 100:.0f}%",
        f"PII redacted in {guards['pii_redacted_cases']} benign queries"], size=14)
    card(s, 7.7, 4.15, 5.2, 2.2, "Classifier & suitability model", [
        f"Preference classifier ({prefs['classifier']}): trip type {prefs.get('travel_type_accuracy', 0) * 100:.0f}%, "
        f"top-dim recall {prefs.get('top_dims_recall', 0) * 100:.0f}%",
        f"Suitability GBT AUC {MODEL['gbt']['auc']} (LogReg {MODEL['logreg_baseline']['auc']})"], size=13)

    # 12 Challenges
    s = slide("Challenges & Learnings")
    bullets(s, ["Dataset lacked the key fields → real preference vectors + transparent simulation, documented; real-CSV loader kept",
                "ChromaDB segfault on Windows → bisected to a pyarrow 18 conflict; pinned versions in an isolated venv",
                "Evaluation exposed ranking bias (one destination for 4/8 scenarios) → tier-aware feasibility and a lower "
                "unmentioned-preference prior → 7 different destinations",
                "\"budget $3000\" parsed as budget *tier* → phrase-level patterns + regression test",
                "LLM vs code: money, filters and citations stay deterministic; the LLM handles language and judgment, "
                "with an offline fallback for every LLM step",
                "The LLM judge is far stricter than rule checks; its critique (pace for kids, double-counted costs) "
                "drove real fixes"], size=17)

    # 13 Q&A
    s = slide("Thank you · Q&A")
    bullets(s, ["Code, docs and evaluation: README.md · design/ · docs/ · eval/results/",
                "Run: python scripts/setup_all.py → uvicorn src.main:app → streamlit run frontend.py"], y=2.5, size=20)

    prs.save(OUT / "Project_Presentation.pptx")
    print("written", OUT / "Project_Presentation.pptx")


if __name__ == "__main__":
    main()
