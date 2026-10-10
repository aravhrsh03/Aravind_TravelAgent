"""Builds the travel-experience corpus from the UCI travel-review rating datasets.

Why this exists
---------------
The capstone brief names "TripAdvisor Travel Review Ratings" (UCI #484) and links UCI #485
(Google travel review ratings). Both are *user x category average rating* matrices: they hold
real preference signal for ~6.4k travelers, but no review_text, destination, travel_type or
visit_date - the key fields the brief requires.

We therefore:
  1. Load the real rating matrices and map their categories onto 8 "Traveler DNA" dimensions.
  2. Turn each traveler's ratings into a relative-interest profile (0-1 per dimension).
  3. Simulate trips for those travelers to curated destinations; ratings are a deterministic
     function of (real profile x destination strengths x season x budget x duration) + noise,
     and review text is composed from that same signal so that text, rating and metadata agree.

The result is a seeded, reproducible corpus with every key field. Any real CSV that already has
the key fields can be dropped in instead via `load_external_experiences`.
"""
from __future__ import annotations

import datetime as dt
import random

import numpy as np
import pandas as pd

from src.config import BUDGET_TIERS, DIMENSIONS, TRAVEL_TYPES, get_settings
from src.services.catalog import Catalog, Destination, get_catalog

SEED = 42

# UCI #485 (Google review ratings, 0-5) category order, per the UCI dataset description.
UCI485_CATS = ["churches", "resorts", "beaches", "parks", "theatres", "museums", "malls", "zoo",
               "restaurants", "pubs_bars", "local_services", "burger_pizza", "hotels", "juice_bars",
               "art_galleries", "dance_clubs", "swimming_pools", "gyms", "bakeries", "beauty_spas",
               "cafes", "view_points", "monuments", "gardens"]
UCI485_MAP = {
    "beach": ["beaches", "swimming_pools"],
    "culture": ["churches", "theatres", "museums", "art_galleries", "monuments"],
    "food": ["restaurants", "burger_pizza", "bakeries", "cafes", "juice_bars"],
    "nightlife": ["pubs_bars", "dance_clubs"],
    "nature": ["parks", "view_points", "gardens"],
    "shopping": ["malls", "local_services"],
    "wellness": ["resorts", "beauty_spas", "gyms", "swimming_pools"],
    "family": ["zoo", "parks"],
}
# UCI #484 (TripAdvisor East Asia, 0-4) category order.
UCI484_CATS = ["art_galleries", "dance_clubs", "juice_bars", "restaurants", "museums", "resorts",
               "parks", "beaches", "theaters", "religious"]
UCI484_MAP = {
    "beach": ["beaches"],
    "culture": ["art_galleries", "museums", "theaters", "religious"],
    "food": ["restaurants", "juice_bars"],
    "nightlife": ["dance_clubs"],
    "nature": ["parks"],
    "shopping": [],  # not present in #484 -> imputed from the traveler's overall activity level
    "wellness": ["resorts"],
    "family": ["parks"],
}
HOME_REGIONS = ["South Asia", "Europe", "North America", "Southeast Asia", "Middle East",
                "East Asia", "Oceania", "Latin America", "Africa"]
HOME_WEIGHTS = [0.30, 0.22, 0.16, 0.08, 0.07, 0.06, 0.04, 0.04, 0.03]


# --------------------------------------------------------------------------- profiles
def _to_interest(raw: np.ndarray) -> np.ndarray:
    """Average ratings -> relative interest in [0, 1] (what a traveler likes *more than usual*)."""
    rel = (raw - raw.mean()) / (raw.std() + 1e-6)
    return 1.0 / (1.0 + np.exp(-1.4 * rel))


def load_traveler_profiles(rng: np.random.Generator) -> pd.DataFrame:
    s = get_settings()
    rows = []

    g = pd.read_csv(s.raw_dir / "uci485_google_review_ratings.csv")
    g = g.loc[:, ~g.columns.str.startswith("Unnamed")]
    g.columns = ["user"] + UCI485_CATS
    g[UCI485_CATS] = g[UCI485_CATS].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    for _, r in g.iterrows():
        raw = np.array([r[UCI485_MAP[d]].mean() for d in DIMENSIONS])
        rows.append(("G" + r["user"].split()[-1], "uci485_google", raw / 5.0))

    t = pd.read_csv(s.raw_dir / "uci484_tripadvisor_review.csv")
    t.columns = ["user"] + UCI484_CATS
    for _, r in t.iterrows():
        vals = r[UCI484_CATS].astype(float) / 4.0
        raw = []
        for d in DIMENSIONS:
            cols = UCI484_MAP[d]
            raw.append(vals[cols].mean() if cols else float(vals.mean() + rng.normal(0, 0.08)))
        rows.append(("T" + r["user"].split()[-1], "uci484_tripadvisor", np.array(raw)))

    recs = []
    for uid, src, raw in rows:
        interest = _to_interest(raw)
        rec = {"user_id": uid, "source_dataset": src}
        rec.update({f"pref_{d}": round(float(v), 4) for d, v in zip(DIMENSIONS, interest)})
        rec["home_region"] = rng.choice(HOME_REGIONS, p=HOME_WEIGHTS)
        recs.append(rec)
    return pd.DataFrame(recs)


# --------------------------------------------------------------------------- simulation
def preference_match(pref: np.ndarray, dest: Destination) -> float:
    """Interest-weighted average of destination strengths, in [0, 1]."""
    w = pref ** 2
    return float(w @ dest.vector / (w.sum() + 1e-9))


def _pick_travel_type(pref: dict[str, float], rng: np.random.Generator) -> str:
    w = np.array([
        0.8 + pref["culture"] + pref["nature"],             # solo
        0.8 + pref["wellness"] + pref["food"],              # couple
        0.4 + 2.2 * pref["family"],                         # family
        0.5 + 1.6 * pref["nightlife"] + 0.5 * pref["beach"],  # friends
        0.25,                                               # business
    ])
    return str(rng.choice(TRAVEL_TYPES, p=w / w.sum()))


def _pick_budget(pref: dict[str, float], rng: np.random.Generator) -> str:
    w = np.array([1.2, 1.5 + 0.3 * pref["shopping"], 0.4 + 1.0 * pref["wellness"]])
    return str(rng.choice(BUDGET_TIERS, p=w / w.sum()))


def rating_model(pref: np.ndarray, dest: Destination, travel_type: str, tier: str, month: int,
                 days: int, noise: float = 0.0) -> tuple[float, dict[str, float]]:
    """Ground-truth satisfaction model. Returns a continuous score (1-5) and its factor breakdown."""
    f: dict[str, float] = {}
    f["preference"] = 3.4 * (preference_match(pref, dest) - 0.55)
    f["season"] = 0.35 if month in dest.best_months else -0.65
    pricey = dest.daily_cost["mid"]
    f["budget"] = {"budget": -0.9 if pricey >= 200 else (-0.35 if pricey >= 140 else 0.15),
                   "mid": -0.25 if pricey >= 250 else 0.05,
                   "luxury": 0.25}[tier]
    if days < dest.min_days:
        f["duration"] = -0.25 * (dest.min_days - days)
    elif days > dest.max_days:
        f["duration"] = -0.08 * (days - dest.max_days)
    else:
        f["duration"] = 0.1 if abs(days - dest.ideal_days) <= 1 else 0.0
    f["party_fit"] = {
        "family": 1.1 * (dest.strengths["family"] - 0.55) - 0.4 * max(0.0, dest.strengths["nightlife"] - 0.85),
        "friends": 0.8 * (dest.strengths["nightlife"] - 0.5),
        "couple": 0.6 * (dest.strengths["wellness"] - 0.5),
        "solo": 0.4 * (dest.strengths["culture"] - 0.5),
        "business": 0.3 * (dest.strengths["food"] - 0.5),
    }[travel_type]
    score = 3.2 + sum(f.values()) + noise
    return float(np.clip(score, 1.0, 5.0)), f


# --------------------------------------------------------------------------- review text
_OPEN = {
    "solo": ["Travelled solo to {d} for {n} days.", "My first solo trip to {d} - {n} days on my own.",
             "Spent {n} days exploring {d} by myself."],
    "couple": ["{n}-day trip to {d} with my partner.", "We went to {d} as a couple for {n} days.",
               "Anniversary getaway: {n} days in {d}."],
    "family": ["Family holiday in {d} with the kids, {n} days.", "Took the whole family (two kids) to {d} for {n} days.",
               "{n} days in {d} with my family."],
    "friends": ["Group trip with friends to {d}, {n} days.", "Five of us went to {d} for {n} days.",
                "Friends' getaway to {d} - {n} days of fun."],
    "business": ["Work trip to {d}; added {n} days of leisure.", "Was in {d} for a conference and stayed {n} days."],
}
_ACT_POS = ["{a} was a real highlight.", "Loved {a} - absolutely worth it.", "{a} exceeded expectations.",
            "Do not miss {a}.", "{a} was the best part of the trip for us."]
_ACT_MID = ["{a} was nice but a bit overrated.", "{a} was fine, nothing special.", "{a} was okay but crowded."]
_ACT_NEG = ["{a} was disappointing and felt like a tourist trap.", "Skip {a} - not worth the money or time.",
            "{a} was a letdown for us."]
_SEASON_GOOD = {"beach": "The weather in {m} was perfect - calm seas and sunshine.",
                "nature": "Visiting in {m} meant clear skies and great views.",
                "default": "{m} was a great time to visit, pleasant weather throughout."}
_SEASON_BAD = {"beach": "Going in {m} was a mistake - rough seas and lots of rain.",
               "nature": "In {m} the weather ruined a couple of the outdoor days.",
               "default": "{m} is not the best season; the weather was unpleasant and some places were closed."}
_BUDGET = {
    ("budget", "neg"): "On a tight budget it felt very expensive - costs added up fast.",
    ("budget", "pos"): "Great value for money; easy to travel on a budget here.",
    ("mid", "neg"): "Prices were higher than we expected for mid-range hotels.",
    ("mid", "pos"): "Mid-range hotels were comfortable and fairly priced.",
    ("luxury", "pos"): "We splurged on a luxury stay and it was worth every penny.",
    ("luxury", "neg"): "Even the luxury hotel felt overpriced for what it offered.",
}
_DUR_SHORT = "{n} days was too short - we felt rushed and missed a lot."
_DUR_LONG = "{n} days was a bit too long; we ran out of things to do."
_CLOSE_POS = ["Highly recommend {d} for {t} travellers.", "Would definitely go back.",
              "One of our best trips - 10/10 for {t} travel.", "Perfect for anyone who loves {c}."]
_CLOSE_MID = ["Decent trip overall, but plan carefully.", "Good, not great - manage your expectations.",
              "Worth a visit if you are into {c}."]
_CLOSE_NEG = ["Would not recommend {d} for {t} travellers.", "Not for us - would choose somewhere else next time.",
              "Overall a disappointing trip for {t} travel."]
_TITLE = {5: ["Unforgettable!", "Absolutely loved it", "Perfect trip"], 4: ["Great trip", "Really enjoyable", "Lovely holiday"],
          3: ["Mixed feelings", "Good but not great", "Average experience"], 2: ["Underwhelming", "Not what we hoped"],
          1: ["Disappointing", "Would not go again"]}
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"]


def compose_review(rnd: random.Random, dest: Destination, pref: dict[str, float], travel_type: str,
                   tier: str, month: int, days: int, rating: int, factors: dict[str, float],
                   acts: list) -> tuple[str, str]:
    parts = [rnd.choice(_OPEN[travel_type]).format(d=dest.name, n=days)]
    for a in acts:
        lean = (rating - 3) * 0.5 + (pref[a.dimension] - 0.5) * 1.5 + dest.strengths[a.dimension] - 0.6 + rnd.gauss(0, 0.4)
        bank = _ACT_POS if lean > 0.35 else (_ACT_NEG if lean < -0.45 else _ACT_MID)
        parts.append(rnd.choice(bank).format(a=a.name))
    key_dim = max(DIMENSIONS, key=lambda d: pref[d] * dest.strengths[d])
    season_bank = _SEASON_GOOD if factors["season"] > 0 else _SEASON_BAD
    if rnd.random() < 0.8:
        parts.append(season_bank.get(key_dim, season_bank["default"]).format(m=_MONTHS[month - 1]))
    if rnd.random() < 0.75:
        parts.append(_BUDGET[(tier, "neg" if factors["budget"] < -0.2 else "pos")])
    if factors["duration"] < -0.2:
        parts.append(_DUR_SHORT.format(n=days))
    elif factors["duration"] < -0.05 and rnd.random() < 0.6:
        parts.append(_DUR_LONG.format(n=days))
    if travel_type == "family":
        parts.append("Very kid-friendly." if dest.strengths["family"] >= 0.6 else "Not ideal with young children.")
    if travel_type == "friends" and dest.strengths["nightlife"] >= 0.75:
        parts.append("The nightlife was buzzing every night.")
    closing = _CLOSE_POS if rating >= 4 else (_CLOSE_MID if rating == 3 else _CLOSE_NEG)
    parts.append(rnd.choice(closing).format(d=dest.name, t=travel_type, c=key_dim))
    title = rnd.choice(_TITLE[rating])
    return title, " ".join(parts)


def simulate_trip(rng: np.random.Generator, rnd: random.Random, catalog: Catalog, user: pd.Series,
                  idx: int) -> dict:
    pref_vec = np.array([user[f"pref_{d}"] for d in DIMENSIONS])
    pref = dict(zip(DIMENSIONS, pref_vec))
    travel_type = _pick_travel_type(pref, rng)
    tier = _pick_budget(pref, rng)

    # Travelers mostly pick destinations that suit them, but ~25% pick poorly -> negative examples.
    if rng.random() < 0.25:
        dest = catalog.destinations[rng.integers(len(catalog.destinations))]
    else:
        logits = np.array([6.0 * preference_match(pref_vec, d) + (0.8 * d.strengths["family"] if travel_type == "family" else 0)
                           for d in catalog.destinations])
        p = np.exp(logits - logits.max())
        dest = catalog.destinations[rng.choice(len(p), p=p / p.sum())]

    month = int(rng.choice(dest.best_months)) if rng.random() < 0.65 else int(rng.integers(1, 13))
    days = int(np.clip(round(rng.normal(dest.ideal_days, 2.2)), 2, 16))
    raw, factors = rating_model(pref_vec, dest, travel_type, tier, month, days, noise=float(rng.normal(0, 0.45)))
    rating = int(np.clip(round(raw), 1, 5))

    weights = np.array([0.15 + pref[a.dimension] * (1.3 if a.dimension == "family" and travel_type == "family" else 1.0)
                        for a in dest.activities])
    n_act = int(min(len(dest.activities), rng.integers(2, 5)))
    act_idx = rng.choice(len(dest.activities), size=n_act, replace=False, p=weights / weights.sum())
    acts = [dest.activities[i] for i in act_idx]
    title, text = compose_review(rnd, dest, pref, travel_type, tier, month, days, rating, factors, acts)

    year = int(rng.choice([2019, 2021, 2022, 2023, 2024, 2025], p=[0.12, 0.08, 0.18, 0.22, 0.22, 0.18]))
    day = int(rng.integers(1, 29))
    spend = dest.daily_cost[tier] * float(rng.lognormal(0, 0.18))
    category = max(DIMENSIONS, key=lambda d: pref[d] * dest.strengths[d])
    return {
        "review_id": f"R{idx:05d}",
        "user_id": user["user_id"],
        "destination": dest.name,
        "country": dest.country,
        "region": dest.region,
        "category": category,
        "rating": rating,
        "title": title,
        "review_text": text,
        "travel_type": travel_type,
        "visit_date": dt.date(year, month, day).isoformat(),
        "visit_month": month,
        "duration_days": days,
        "budget_tier": tier,
        "spend_per_day_usd": round(spend, 2),
        "trip_cost_usd": round(spend * days, 2),
        "activities": " | ".join(a.name for a in acts),
        "home_region": user["home_region"],
        "source_dataset": user["source_dataset"],
    }


def build_corpus(extra_trip_rate: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    rnd = random.Random(SEED)
    catalog = get_catalog()
    users = load_traveler_profiles(rng)
    records, idx = [], 1
    for _, u in users.iterrows():
        for _ in range(1 + int(rng.random() < extra_trip_rate)):
            records.append(simulate_trip(rng, rnd, catalog, u, idx))
            idx += 1
    return users, pd.DataFrame(records)


def load_external_experiences(path: str) -> pd.DataFrame:
    """Hook for a real dataset that already has the brief's key fields."""
    df = pd.read_csv(path)
    required = {"user_id", "destination", "category", "rating", "review_text", "travel_type", "visit_date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"External dataset missing required columns: {sorted(missing)}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Preprocessing applied to any corpus (generated or external)."""
    df = df.drop_duplicates(subset=["user_id", "destination", "visit_date", "review_text"]).copy()
    df["review_text"] = df["review_text"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    df = df[df["review_text"].str.len() >= 20]
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce").clip(1, 5)
    df = df.dropna(subset=["rating"])
    df["rating"] = df["rating"].astype(int)
    df["travel_type"] = df["travel_type"].str.lower().where(df["travel_type"].str.lower().isin(TRAVEL_TYPES), "solo")
    return df.reset_index(drop=True)
