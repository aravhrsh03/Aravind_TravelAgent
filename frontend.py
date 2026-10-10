"""WanderVision front end:  streamlit run frontend.py   (expects the API at WANDERVISION_API, default http://127.0.0.1:8000)"""
from __future__ import annotations

import html
import json
import os
import re

import plotly.graph_objects as go
import requests
import streamlit as st

API = os.getenv("WANDERVISION_API", "http://127.0.0.1:8000")
DIMS = ["beach", "culture", "food", "nightlife", "nature", "shopping", "wellness", "family"]
NOT_SET, ANY, NOT_SPECIFIED, OWN = "Let the app decide", "Any", "Not specified", "Write my own"
REGIONS = [NOT_SPECIFIED, "South Asia", "Southeast Asia", "East Asia", "Middle East", "Europe", "Africa", "North America",
           "Latin America", "Oceania"]
MONTHS = [ANY, "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SAMPLES = [
    "A couple wants a 5-day trip focused on beaches, sightseeing and local food in December, budget $3000, flying from India",
    "Family of 4 with two kids, limited budget of $2500, 6 days, want highly rated activities and kid-friendly places",
    "Solo traveler from Europe, 7 days in October, loves hiking, nature and history, budget-friendly",
    "Group of friends, 5 days of nightlife, beaches and street food in March, around 1200 USD each",
    "Luxury honeymoon with spa and beaches for 6 days in February, budget 8000 USD, from India",
]

# Palette: warm paper background, terracotta accent, deep teal and ochre as supporting colours.
INK, MUTED = "#2A2723", "#6E675D"
TERRACOTTA, TEAL, OCHRE, PLUM = "#B4492A", "#2F6F6B", "#C99A3B", "#7A4E6D"
SAND = "#E7DECF"

st.set_page_config(page_title="WanderVision", layout="wide")
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stTextInput, .stTextArea, button {{font-family: 'Inter', system-ui, sans-serif;}}
h1, h2, h3, h4 {{font-family: 'Fraunces', Georgia, serif !important; font-weight: 600 !important; letter-spacing: -.01em; color: {INK};}}
.block-container {{padding-top: 2.2rem; max-width: 1180px;}}
header[data-testid="stHeader"] {{background: transparent;}}

.wv-brand {{font-family:'Fraunces',Georgia,serif; font-size: 2.5rem; font-weight:600; line-height:1; color:{INK}; margin:0;}}
.wv-brand span {{color:{TERRACOTTA};}}
.wv-tag {{color:{MUTED}; font-size:1.02rem; margin: .45rem 0 1.4rem 0; max-width: 46rem; line-height:1.5;}}
.wv-gap {{height: 1rem;}}

.wv-p {{margin: 0 0 .6rem 0; line-height: 1.55;}}
.wv-list {{margin: .2rem 0 .9rem 1.2rem; padding: 0;}}
.wv-list li {{margin: .3rem 0; line-height: 1.5;}}
.wv-pills {{margin: .1rem 0 .5rem 0;}}
.wv-pill {{display:inline-block; padding: 3px 11px; border-radius: 999px; font-size: .8rem; margin: 3px 5px 3px 0;
          background: {SAND}; color: {INK};}}
.wv-pill.warn {{background:#F6E3C4; color:#7A5410;}}
.wv-pill.ok {{background:#D9E9E6; color:#1F4F4B;}}
.wv-pill.accent {{background:#F4DCD3; color:#8A3519;}}
.wv-muted {{color:{MUTED}; font-size:.88rem; line-height: 1.45;}}
.wv-item {{margin: 0 0 .75rem 0;}}
.wv-slot {{display:inline-block; min-width: 5.2rem; font-size:.72rem; letter-spacing:.07em; text-transform:uppercase;
          color:{TERRACOTTA}; font-weight:600;}}
.wv-step {{border-left: 3px solid {TEAL}; padding: 6px 0 6px 14px; margin: 8px 0; color:{INK};}}
.wv-score {{font-family:'Fraunces',Georgia,serif; font-size:2.6rem; line-height:1; color:{TEAL};}}
.wv-score small {{font-size:1rem; color:{MUTED}; font-family:'Inter',sans-serif;}}
.wv-label {{font-size:.74rem; letter-spacing:.08em; text-transform:uppercase; color:{MUTED}; font-weight:600;}}

div[data-testid="stVerticalBlockBorderWrapper"] {{border-radius: 14px;}}
div[data-testid="stTabs"] button[role="tab"] {{font-size: .98rem; padding: .55rem .9rem;}}
div[data-testid="stTabs"] button[aria-selected="true"] {{color:{TERRACOTTA}; font-weight:600;}}
button[kind="primary"] {{border-radius: 10px; font-weight:600;}}
section[data-testid="stSidebar"] {{border-right: 1px solid {SAND};}}
section[data-testid="stSidebar"] h2 {{font-size:1.25rem;}}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ safe text rendering
# Everything that comes from the API or a model goes through one of these helpers, so stray HTML, markdown characters or
# dollar signs (which Streamlit would otherwise read as maths) can never leak into the page.
_PUNCT = re.compile(r"([!-/:-@\[-`{-~])")


def clean(x) -> str:
    return " ".join(str(x).split())


def tidy(x) -> str:
    """Segment and title strings from the API use a middle dot as a separator; show them as plain text."""
    return clean(x).replace(" · ", ", ")


def esc(x) -> str:
    """For HTML contexts."""
    return html.escape(clean(x), quote=True).replace("$", "&#36;")


def md_safe(x) -> str:
    """For markdown contexts (headings, alerts, expander labels): backslash-escape every punctuation character."""
    return _PUNCT.sub(r"\\\1", clean(x))


def para(text, cls: str = "", box=st) -> None:
    box.markdown(f'<div class="wv-p {cls}">{esc(text)}</div>', unsafe_allow_html=True)


def note(text, box=st) -> None:
    para(text, "wv-muted", box)


def bullet_list(items, box=st) -> None:
    items = [i for i in items if clean(i)]
    if items:
        box.markdown('<ul class="wv-list">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>", unsafe_allow_html=True)


def heading(text, level: int = 4, box=st) -> None:
    box.markdown("#" * level + " " + md_safe(text))


def pills(items, kind: str = "") -> str:
    return '<div class="wv-pills">' + "".join(f'<span class="wv-pill {kind}">{esc(i)}</span>' for i in items) + "</div>"


def section_label(text: str) -> None:
    st.markdown(f'<div class="wv-label">{esc(text)}</div>', unsafe_allow_html=True)


def rating_text(r) -> str:
    return f"{float(r):g}/5"


# ------------------------------------------------------------------ API helpers
def call(method: str, path: str, **kw):
    try:
        r = requests.request(method, f"{API}{path}", timeout=180, **kw)
    except requests.ConnectionError:
        st.error(md_safe(f"Can't reach the WanderVision API at {API}. Start it with: uvicorn src.main:app, then reload this page."))
        st.stop()
    if r.status_code == 400 and isinstance(r.json().get("detail"), dict):
        d = r.json()["detail"]
        st.warning(md_safe(f"That request was blocked by the safety checks ({d.get('category', 'blocked')}). "
                           + " ".join(d.get("reasons", []))))
        return None
    if r.status_code == 422:
        st.warning("That input could not be used. Please describe the trip in a few words (at least 3 characters).")
        return None
    if r.status_code >= 400:
        st.error(md_safe(f"The API returned an error ({r.status_code}): {r.json().get('detail', r.text)}"))
        return None
    return r.json()


@st.cache_data(ttl=300)
def destinations() -> list[dict]:
    return call("GET", "/api/v1/destinations") or []


@st.cache_data(ttl=3600)
def get_review(rid: str) -> dict | None:
    return call("GET", f"/api/v1/experiences/{rid}")


def style_fig(fig: go.Figure) -> go.Figure:
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"family": "Inter, sans-serif", "color": INK, "size": 12},
                      title_font={"family": "Fraunces, Georgia, serif", "size": 16})
    if not fig.layout.title.text:
        fig.update_layout(title_text="")  # plotly.js would otherwise render the literal word "undefined"
    return fig


def radar(dna: dict, title: str = "", compare: dict | None = None, names=("You", "Twin")):
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=[dna[d] for d in DIMS] + [dna[DIMS[0]]], theta=[d.capitalize() for d in DIMS + [DIMS[0]]],
                                  fill="toself", name=names[0], line_color=TEAL, fillcolor="rgba(47,111,107,.25)"))
    if compare:
        fig.add_trace(go.Scatterpolar(r=[compare[d] for d in DIMS] + [compare[DIMS[0]]],
                                      theta=[d.capitalize() for d in DIMS + [DIMS[0]]], fill="toself", name=names[1],
                                      line_color=TERRACOTTA, fillcolor="rgba(180,73,42,.2)"))
    fig.update_layout(polar={"radialaxis": {"range": [0, 1], "showticklabels": False, "gridcolor": SAND},
                             "angularaxis": {"gridcolor": SAND}, "bgcolor": "rgba(0,0,0,0)"},
                      showlegend=bool(compare), margin={"l": 64, "r": 64, "t": 44 if title else 12, "b": 36}, height=320,
                      title=title)
    return style_fig(fig)


def review_popover(evidence: list[str], index: dict) -> None:
    for rid in evidence:
        r = index.get(rid)
        if r:
            st.markdown(f'<div class="wv-p"><b>{esc(r["destination"])}</b>, {esc(rating_text(r["rating"]))}, '
                        f'{esc(r["travel_type"])} trip, visited {esc(r["visit_date"])}</div>', unsafe_allow_html=True)
            para(r["text"].split("\n", 1)[-1])


def engine_label(llm: dict) -> str:
    return f"Claude ({llm['model']})" if llm.get("model") else "built-in rules (no language model key)"


def params_sidebar() -> dict:
    with st.sidebar:
        st.header("About the trip")
        st.caption("All optional. Anything you leave blank is worked out from your description.")
        p: dict = {}
        if st.checkbox("Set trip length"):
            p["days"] = st.slider("Days", 1, 21, 5)
        if st.checkbox("Set total budget (USD)"):
            p["budget_usd"] = st.number_input("Budget", 100, 100_000, 3000, step=100)
        if st.checkbox("Set number of travelers"):
            p["travelers"] = st.number_input("Travelers", 1, 30, 2)
        tt = st.selectbox("Who is going", [NOT_SET, "solo", "couple", "family", "friends", "business"])
        if tt != NOT_SET:
            p["travel_type"] = tt
        tier = st.selectbox("Spending style", [NOT_SET, "budget", "mid", "luxury"])
        if tier != NOT_SET:
            p["budget_tier"] = tier
        m = st.selectbox("Month of travel", MONTHS)
        if m != ANY:
            p["month"] = MONTHS.index(m)
        o = st.selectbox("Flying from", REGIONS)
        if o != NOT_SPECIFIED:
            p["origin_region"] = o
        if st.checkbox("Adjust interests by hand"):
            p["dna"] = {d: st.slider(d.capitalize(), 0.0, 1.0, 0.5, 0.05) for d in DIMS}
        st.divider()
        health = call("GET", "/health")
        if health:
            note(f"Language model: {engine_label(health['llm'])}")
            note(f"{health['documents']:,} past trips indexed")
        return p


# ------------------------------------------------------------------ pages
def page_plan(params: dict) -> None:
    st.subheader("Plan a trip")
    st.caption("Describe who is travelling and what they want. You'll get ranked destinations, a day-by-day plan, "
               "a cost check and the past trips behind each suggestion.")
    sample = st.selectbox("Start from an example", [OWN] + SAMPLES)
    query = st.text_area("Your request", value="" if sample == OWN else sample, height=96,
                         placeholder="For example: a couple wants 5 days of beaches, sightseeing and local food in December")
    if st.button("Build my plan", type="primary", use_container_width=True) and query.strip():
        with st.spinner("Checking the request, reading similar trips, ranking destinations and drafting the itinerary..."):
            st.session_state["plan"] = call("POST", "/api/v1/plan", json={"query": query, "params": params})
    res = st.session_state.get("plan")
    if not res:
        return
    prof, it, judge = res["profile"], res["itinerary"], res["judge"]
    evidence_index = {e["review_id"]: e for e in res["retrieval"]["evidence"]}

    st.markdown('<div class="wv-gap"></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.1, 1.3, 1.2])
    with c1:
        st.plotly_chart(radar(prof["dna"], "What this traveler enjoys"), use_container_width=True)
    with c2:
        section_label("Traveler profile")
        heading(tidy(prof["segment"]))
        st.markdown(pills([f"{prof['days']} days", f"{prof['travelers']} traveler(s)", prof["travel_type"],
                           f"{prof['budget_tier']} spending",
                           f"${prof['budget_usd']:,.0f} budget" if prof.get("budget_usd") else "no budget given",
                           MONTHS[prof["month"]] if prof.get("month") else "any month",
                           f"from {prof['origin_region']}" if prof.get("origin_region") else "origin not given"]),
                    unsafe_allow_html=True)
        if prof.get("defaults_used"):
            note("Assumed because they were not specified: " + ", ".join(prof["defaults_used"]))
        if res["retrieval"]["relaxed"]:
            note("To find enough similar trips, the search loosened: " + ", ".join(res["retrieval"]["relaxed"]))
        if res["guardrail"].get("warnings"):
            st.info(md_safe(" ".join(res["guardrail"]["warnings"])))
    with c3:
        section_label("Quality check")
        verdict = "Approved" if judge["passed"] else "Needs a second look"
        st.markdown(f'<div class="wv-score">{esc(judge["overall"])}<small> / 5</small></div>', unsafe_allow_html=True)
        st.markdown(pills([verdict], "ok" if judge["passed"] else "warn"), unsafe_allow_html=True)
        who = "Claude" if judge["engine"] == "llm" else "built-in rules"
        note(f"Reviewed by {who}, {res['revisions']} revision(s), {res['latency_ms'] / 1000:.1f} seconds")
        for k, v in judge["scores"].items():
            note(f"{k.replace('_', ' ').capitalize()}: {v}/5")

    t_itin, t_recs, t_cost, t_trace, t_fb = st.tabs(["Itinerary", "Destinations", "Cost and feasibility",
                                                     "How it was made", "Feedback"])
    with t_itin:
        heading(tidy(it["title"]), 3)
        para(it["overview"])
        if res["plan"]["adjustments"]:
            st.warning(md_safe("The plan was adjusted to fit your constraints: " + " ".join(res["plan"]["adjustments"])))
        author = "Claude" if it.get("engine") == "llm" else "built-in rules"
        note(f"{it['citation_coverage'] * 100:.0f}% of the activities are backed by highly rated trips from similar "
             f"travelers. Drafted by {author}.")
        all_reviews = dict(evidence_index)
        for day in it["days"]:
            with st.container(border=True):
                heading(f"Day {day['day']}: {day['theme']}")
                for item in day["items"]:
                    a, b = st.columns([5, 1.4])
                    cost = f", ${item['cost_usd']:.0f} per person" if item.get("cost_usd") else ""
                    a.markdown(
                        f'<div class="wv-item"><span class="wv-slot">{esc(item["slot"])}</span>'
                        f'<b>{esc(item["activity"])}</b>{esc(cost)}'
                        f'<div class="wv-muted">{esc(item.get("note", ""))}</div></div>', unsafe_allow_html=True)
                    if item.get("evidence"):
                        with b.popover(f"{len(item['evidence'])} past review(s)"):
                            for rid in item["evidence"]:
                                if rid not in all_reviews:
                                    all_reviews[rid] = get_review(rid)
                            review_popover(item["evidence"], all_reviews)
        if it.get("tips"):
            heading("Tips from past travelers")
            bullet_list(it["tips"])

    with t_recs:
        for c in res["recommendations"]:
            with st.container(border=True):
                a, b = st.columns([3, 2])
                heading(f"{c['rank']}. {c['destination']}, {c['country']}", 4, a)
                a.markdown(pills([c["label"]], "accent" if c["rank"] == 1 else ""), unsafe_allow_html=True)
                para(c["summary"], box=a)
                bullet_list(c["reasons"], a)
                sig = c["signals"]
                fig = go.Figure(go.Bar(x=list(sig.values()), y=[k.replace("_", " ") for k in sig], orientation="h",
                                       marker_color=TEAL))
                fig.update_layout(height=190, margin={"l": 10, "r": 10, "t": 30, "b": 10}, xaxis={"range": [0, 1]},
                                  yaxis={"autorange": "reversed"}, title=f"Match score {c['priority']:.2f}")
                b.plotly_chart(style_fig(fig), use_container_width=True, key=f"sig-{c['destination']}")
                section_label("Top activities")
                st.markdown(pills([f"{x['activity']} ({x['dimension']})" for x in c["activities"][:5]]),
                            unsafe_allow_html=True)

    with t_cost:
        an = res["plan"]["analysis"]
        est = it["cost"]["estimate"]
        a, b = st.columns(2)
        with a:
            parts = {k.replace("_", " "): est[k] for k in ("stay_food_local", "activities", "flights", "contingency") if est[k]}
            fig = go.Figure(go.Pie(labels=list(parts), values=list(parts.values()), hole=.55,
                                   marker={"colors": [TEAL, TERRACOTTA, OCHRE, PLUM]}))
            fig.update_layout(height=300, margin={"t": 40, "b": 0}, title=f"Estimated total ${est['total']:,}")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with b:
            status = it["cost"]["budget_status"]
            st.metric("Budget", status.replace("_", " "),
                      f"{it['cost']['budget_utilization'] * 100:.0f}% of budget" if it["cost"]["budget_utilization"] else None,
                      delta_color="off")
            st.metric("Trip length", it["cost"]["duration_status"].replace("_", " "))
            section_label("Total by spending style")
            st.markdown(pills([f"{k}: ${v:,}" for k, v in an["cost_by_tier"].items()]), unsafe_allow_html=True)
            if not est["flights_included"]:
                note("Flights are not included. Choose 'Flying from' in the sidebar to add them.")
        bullet_list(it["cost"]["notes"])
        best = res["recommendations"][0]["suitability"] if res["recommendations"] else None
        if best:
            heading(f"Chance this trip works out well for {best['destination']}: {best['probability'] * 100:.0f}% "
                    f"({best['label']})", 5)
            st.markdown(pills([f"{f['factor']}: {f['impact']:+.2f}" for f in best["factors"]]), unsafe_allow_html=True)

    with t_trace:
        note("Several specialist steps work on the request in turn and pass notes to each other. "
             "Open a step to see exactly what it produced.")
        for step in res["trace"]:
            kind = "Claude" if step["engine"] == "llm" else "rules"
            label = tidy(f"{step['agent']}: {step['summary']} ({kind}, {step['duration_ms']:.0f} ms)")
            with st.expander(md_safe(label)):
                note(step["role"])
                st.json(step["details"], expanded=False)
        heading("Notes passed between steps")
        for m in res["messages"]:
            st.markdown(f'<div class="wv-step"><b>{esc(m["from"])} to {esc(m["to"])}</b><br>{esc(m["content"])}</div>',
                        unsafe_allow_html=True)

    with t_fb:
        para("Tell us how well this worked. Your rating nudges future rankings, and a helpful comment of 8 or more "
             "words can be added to the searchable trip history once it passes the safety checks.")
        with st.form("fb"):
            dest = st.selectbox("Destination", [c["destination"] for c in res["recommendations"]])
            rating = st.slider("How good was this recommendation?", 1, 5, 4)
            helpful = st.radio("Was it helpful?", ["yes", "no"], horizontal=True) == "yes"
            comment = st.text_area("Anything to add? (optional)")
            if st.form_submit_button("Send feedback"):
                out = call("POST", "/api/v1/feedback", json={"request_id": res["request_id"], "destination": dest,
                                                             "rating": rating, "helpful": helpful,
                                                             "comment": comment or None,
                                                             "travel_type": prof["travel_type"]})
                if out:
                    saved = (f", and your comment was saved as experience {out['indexed_as_experience']}"
                             if out["indexed_as_experience"] else "")
                    st.success(md_safe(f"Thank you. The ranking adjustment for {dest} is now "
                                       f"{out['new_ranking_boost']:+.3f}{saved}."))


def page_search(params: dict) -> None:
    st.subheader("Search past trips")
    st.caption("Find historical traveler experiences that match a description, with optional filters.")
    q = st.text_input("What are you looking for?", "5-day trip focused on beaches, sightseeing and local food")
    names = [d["name"] for d in destinations()]
    c1, c2, c3, c4 = st.columns(4)
    f = {"destinations": c1.multiselect("Destination", names) or None,
         "travel_types": c2.multiselect("Who travelled", ["solo", "couple", "family", "friends", "business"]) or None,
         "budget_tiers": c3.multiselect("Spending style", ["budget", "mid", "luxury"]) or None,
         "min_rating": c4.slider("Minimum rating", 1, 5, 4)}
    c5, c6, c7 = st.columns(3)
    mode = c5.radio("Search method", ["hybrid", "dense", "keyword"], horizontal=True,
                    help="Hybrid combines meaning-based and keyword matching. Try the other two to compare.")
    top_k = c6.slider("Number of results", 3, 30, 10)
    personalize = c7.toggle("Favour my interests", True)
    if st.button("Search", type="primary"):
        res = call("POST", "/api/v1/search", json={"query": q, "params": params, "filters": {k: v for k, v in f.items() if v},
                                                   "top_k": top_k, "mode": mode, "personalize": personalize})
        if not res:
            return
        note(f"{len(res['results'])} results in {res['latency_ms']:.0f} ms. Traveler type: {tidy(res['segment'])}")
        if res["destination_summaries"]:
            heading("Where these trips went")
            cols = st.columns(min(3, len(res["destination_summaries"])))
            for i, s in enumerate(res["destination_summaries"][:3]):
                with cols[i].container(border=True):
                    st.markdown(f'<div class="wv-p"><b>{esc(s["destination"])}</b><br>{esc(s["matches"])} matches, '
                                f'average {esc(s["avg_rating"])}/5</div>', unsafe_allow_html=True)
                    if s["praised_activities"]:
                        note("Loved: " + "; ".join(a["activity"] for a in s["praised_activities"]))
                    if s["common_complaints"]:
                        note("Complaints: " + "; ".join(c["issue"] for c in s["common_complaints"]))
        heading("Matching trips")
        for r in res["results"]:
            with st.container(border=True):
                head, body = r["text"].split("\n", 1)
                st.markdown(f'<div class="wv-p"><b>{esc(r["destination"])}</b>, {esc(rating_text(r["rating"]))} '
                            f'<span class="wv-muted">{esc(r["review_id"])}, {esc(head)}</span></div>', unsafe_allow_html=True)
                para(body)
                s = r["scores"]
                note(f"Match {s['priority']:.2f}, relevance {s['relevance']:.2f}, meaning {s['dense']:.2f}, "
                     f"keywords {s['bm25']:.1f}, fits interests {s['preference_fit']:.2f}, feedback {s['feedback']:.2f}")


def page_twins() -> None:
    st.subheader("Travel twins")
    st.caption("Find past travelers whose tastes match, and see where they were happiest.")
    q = st.text_input("Describe the traveler", "Loves museums, temples, history and trying local food")
    k = st.slider("How many twins", 3, 15, 6)
    if st.button("Find twins", type="primary"):
        res = call("POST", "/api/v1/twins", json={"query": q, "k": k})
        if not res:
            return
        a, b = st.columns([1, 1.2])
        a.plotly_chart(radar(res["traveler_dna"], "You and your closest twin", res["twins"][0]["dna"]), use_container_width=True)
        with b:
            heading("Where people like you were happiest")
            fav = res["twin_favourites"]
            fig = go.Figure(go.Bar(x=[f["bayes_rating"] for f in fav], y=[f["destination"] for f in fav], orientation="h",
                                   text=[f"{f['twin_reviews']} reviews" for f in fav], marker_color=TERRACOTTA))
            fig.update_layout(height=320, margin={"t": 10, "l": 10}, yaxis={"autorange": "reversed"}, xaxis={"range": [3, 5]})
            st.plotly_chart(style_fig(fig), use_container_width=True)
            note("Ratings are similarity-weighted and adjusted so a handful of reviews can't dominate.")
        heading("The twins")
        for t in res["twins"]:
            trips = ", ".join(f"{x['destination']} {rating_text(x['rating'])}" for x in t["trips"])
            st.markdown(f'<div class="wv-p"><b>{esc(t["user_id"])}</b>, {t["similarity"]:.0%} similar, '
                        f'from {esc(t["source_dataset"])}: {esc(trips)}</div>', unsafe_allow_html=True)


def page_feasibility() -> None:
    st.subheader("Budget check")
    st.caption("Change the budget, length or season and see how realistic the trip is.")
    names = [d["name"] for d in destinations()]
    c1, c2, c3, c4 = st.columns(4)
    dest = c1.selectbox("Destination", names)
    days = c2.slider("Days", 1, 21, 5)
    travelers = c3.number_input("Travelers", 1, 20, 2)
    tier = c4.select_slider("Spending style", ["budget", "mid", "luxury"], "mid")
    c5, c6, c7 = st.columns(3)
    budget = c5.number_input("Total budget (USD, 0 for none)", 0, 200_000, 3000, step=250)
    month = c6.selectbox("Month", MONTHS)
    origin = c7.selectbox("Flying from", REGIONS, index=1)
    body = {"destination": dest, "days": days, "travelers": travelers, "budget_tier": tier,
            "budget_usd": budget or None, "month": None if month == ANY else MONTHS.index(month),
            "origin_region": None if origin == NOT_SPECIFIED else origin}
    res = call("POST", "/api/v1/feasibility", json=body)
    q = st.text_input("Interests (used for the satisfaction forecast)", "beaches, food and relaxing")
    suit = call("POST", "/api/v1/suitability", json={"destination": dest, "query": q, "travel_type": "couple" if travelers == 2
                                                       else "family" if travelers > 2 else "solo", "budget_tier": tier,
                                                       "month": body["month"], "days": days})
    if not res:
        return
    a, b, c = st.columns(3)
    a.metric("Estimated total", f"${res['estimate']['total']:,}")
    b.metric("Budget", res["budget_status"].replace("_", " "),
             f"{res['budget_utilization'] * 100:.0f}% used" if res["budget_utilization"] else None, delta_color="off")
    if suit:
        c.metric("Likely to be enjoyed", f"{suit['probability'] * 100:.0f}%", suit["label"], delta_color="off")
    x, y = st.columns(2)
    tiers = res["cost_by_tier"]
    fig = go.Figure(go.Bar(x=list(tiers), y=list(tiers.values()), marker_color=[TEAL, OCHRE, PLUM]))
    if budget:
        fig.add_hline(y=budget, line_dash="dash", line_color=TERRACOTTA, annotation_text="your budget")
    fig.update_layout(height=300, title="Total cost by spending style", margin={"t": 44})
    x.plotly_chart(style_fig(fig), use_container_width=True)
    if suit:
        f = suit["factors"]
        fig2 = go.Figure(go.Bar(x=[v["impact"] for v in f], y=[v["factor"] for v in f], orientation="h",
                                marker_color=[TEAL if v["impact"] > 0 else TERRACOTTA for v in f]))
        fig2.update_layout(height=300, title="What is driving the forecast", margin={"t": 44})
        y.plotly_chart(style_fig(fig2), use_container_width=True)
    bullet_list(res["notes"])
    if res.get("max_affordable_days") is not None:
        note(f"Longest stay you could afford at {tier} spending: {res['max_affordable_days']} days.")


def page_insights() -> None:
    st.subheader("How the system is doing")
    st.caption("Usage numbers, what the feedback loop has learned, and the latest quality evaluation.")
    m = call("GET", "/api/v1/metrics")
    fb = call("GET", "/api/v1/feedback/stats")
    if m:
        heading("Endpoint activity")
        st.dataframe([{"Endpoint": e["endpoint"], "Requests": e["requests"], "Average time (ms)": e["avg_latency_ms"],
                       "Average judge score": e["avg_judge_score"], "Blocked": e["blocked"]} for e in m["endpoints"]],
                     use_container_width=True, hide_index=True)
        llm = m["llm"]
        note(f"Language model: {engine_label(llm)}. {llm['calls']} calls this session, {llm['failures']} failed, "
             f"estimated cost ${llm['est_cost_usd']:.2f}.")
        if llm.get("last_error"):
            low = llm["last_error"].lower()
            st.warning(md_safe("The language model reported a problem: " + (
                "the account has run out of credits, so the app is using its built-in rules."
                if "credit balance" in low else llm["last_error"][:200])))
    if fb:
        heading("Feedback so far")
        a, b, c = st.columns(3)
        a.metric("Responses", fb["total_feedback"])
        b.metric("Average rating", fb["avg_rating"] or "n/a")
        c.metric("Found it helpful", f"{fb['helpful_rate'] * 100:.0f}%" if fb["helpful_rate"] is not None else "n/a")
        if fb["per_destination"]:
            note("Ranking adjustments learned from feedback (kept small until enough votes arrive)")
            st.dataframe([{"Destination": r["destination"], "Ratings": r["count"], "Average rating": r["avg_rating"],
                           "Ranking adjustment": r["ranking_boost"]} for r in fb["per_destination"]],
                         use_container_width=True, hide_index=True)
    report = "eval/results/latest_results.json"
    if os.path.exists(report):
        with open(report, encoding="utf-8") as fh:
            ev = json.load(fh)
        de, plans = ev.get("deepeval", {}), (ev.get("plans_claude") or {}).get("plans", [])
        if de.get("status") == "ok":
            heading("Latest quality evaluation")
            note(f"Scored by Claude on {de['n']} generated plans.")
            st.dataframe([{"Measure": k.replace(" [GEval]", ""), "Average score": v["mean_score"],
                           "Plans passing": f"{v['pass_rate'] * 100:.0f}%"} for k, v in de["metrics"].items()],
                         use_container_width=True, hide_index=True)
            if plans:
                avg = sum(p["judge_overall"] for p in plans) / len(plans)
                note(f"In the same test, Claude rated the plans {avg:.1f} out of 5 on average, "
                     f"and approved {sum(p['passed'] for p in plans)} of {len(plans)}.")


# ------------------------------------------------------------------ layout
st.markdown('<p class="wv-brand">Wander<span>Vision</span></p>', unsafe_allow_html=True)
st.markdown('<p class="wv-tag">Trip planning for travel professionals, grounded in 7,700 historical traveler experiences. '
            'Describe a traveler and get destinations, a day-by-day plan and a budget check, each backed by '
            'similar past trips.</p>', unsafe_allow_html=True)
params = params_sidebar()
tabs = st.tabs(["Plan a trip", "Search past trips", "Travel twins", "Budget check", "Insights"])
with tabs[0]:
    page_plan(params)
with tabs[1]:
    page_search(params)
with tabs[2]:
    page_twins()
with tabs[3]:
    page_feasibility()
with tabs[4]:
    page_insights()
