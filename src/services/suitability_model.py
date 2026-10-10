"""Itinerary suitability prediction: P(traveler rates the trip >= 4 stars).

Gradient-boosted trees over interpretable features (preference fit, season, budget pressure,
duration fit, party fit). Explanations come from counterfactual deltas: each factor group is reset
to a neutral value and the change in probability is reported, so the UI can say e.g.
"travelling in the monsoon costs -18 points".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from src.config import BUDGET_TIERS, DIMENSIONS, TRAVEL_TYPES, get_settings
from src.services.catalog import Destination, get_catalog
from src.services.dataset_builder import preference_match

FEATURES = (["pref_match"] + [f"fit_{d}" for d in DIMENSIONS] +
            ["in_season", "budget_ord", "dest_cost_mid", "cost_pressure", "days_vs_ideal",
             "days_short", "days_long"] + [f"tt_{t}" for t in TRAVEL_TYPES] +
            ["dest_family", "dest_nightlife", "dest_wellness", "dest_culture"])

GROUPS = {
    "preference fit": ["pref_match"] + [f"fit_{d}" for d in DIMENSIONS],
    "season": ["in_season"],
    "budget vs destination cost": ["budget_ord", "cost_pressure"],
    "trip length": ["days_vs_ideal", "days_short", "days_long"],
}


def featurize(dna: dict[str, float], dest: Destination, travel_type: str, tier: str, month: int | None,
              days: int) -> dict[str, float]:
    vec = np.array([dna.get(d, 0.5) for d in DIMENSIONS])
    f = {"pref_match": preference_match(vec, dest)}
    for d in DIMENSIONS:
        f[f"fit_{d}"] = dna.get(d, 0.5) * dest.strengths[d]
    # Unknown month -> assume the planner schedules the trip in season (training data always has a month)
    f["in_season"] = 1.0 if month is None else float(month in dest.best_months)
    f["budget_ord"] = float(BUDGET_TIERS.index(tier))
    f["dest_cost_mid"] = dest.daily_cost["mid"] / 100
    f["cost_pressure"] = dest.daily_cost["mid"] / {"budget": 60, "mid": 160, "luxury": 450}[tier]
    f["days_vs_ideal"] = (days - dest.ideal_days) / dest.ideal_days
    f["days_short"] = float(max(0, dest.min_days - days))
    f["days_long"] = float(max(0, days - dest.max_days))
    for t in TRAVEL_TYPES:
        f[f"tt_{t}"] = float(travel_type == t)
    for d in ("family", "nightlife", "wellness", "culture"):
        f[f"dest_{d}"] = dest.strengths[d]
    return f


def build_training_frame() -> tuple[pd.DataFrame, pd.Series]:
    s = get_settings()
    exp = pd.read_csv(s.experiences_path)
    prof = pd.read_csv(s.travelers_path).set_index("user_id")
    cat = get_catalog()
    rows = []
    for r in exp.itertuples():
        p = prof.loc[r.user_id]
        dna = {d: p[f"pref_{d}"] for d in DIMENSIONS}
        rows.append(featurize(dna, cat.get(r.destination), r.travel_type, r.budget_tier, r.visit_month, r.duration_days))
    return pd.DataFrame(rows)[FEATURES], (exp["rating"] >= 4).astype(int)


def train() -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
    from sklearn.model_selection import train_test_split

    X, y = build_training_frame()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_depth=4, random_state=42)
    model.fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]
    base = LogisticRegression(max_iter=2000).fit(Xtr, ytr)
    pb = base.predict_proba(Xte)[:, 1]
    metrics = {
        "n_train": len(Xtr), "n_test": len(Xte), "positive_rate": round(float(y.mean()), 3),
        "gbt": {"auc": round(roc_auc_score(yte, p), 4), "accuracy": round(accuracy_score(yte, p > 0.5), 4),
                "brier": round(brier_score_loss(yte, p), 4)},
        "logreg_baseline": {"auc": round(roc_auc_score(yte, pb), 4), "accuracy": round(accuracy_score(yte, pb > 0.5), 4)},
        "majority_baseline_accuracy": round(float(max(yte.mean(), 1 - yte.mean())), 4),
    }
    s = get_settings()
    joblib.dump(model, s.model_path)
    s.model_path.with_suffix(".metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


@dataclass
class Suitability:
    destination: str
    probability: float
    label: str
    factors: list[dict]

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@lru_cache
def _model():
    path = get_settings().model_path
    if not path.exists():
        raise FileNotFoundError("Suitability model missing - run `python scripts/train_model.py`.")
    return joblib.load(path)


_NEUTRAL = {"in_season": 1.0, "budget_ord": None, "cost_pressure": 1.0, "days_vs_ideal": 0.0, "days_short": 0.0,
            "days_long": 0.0}


def predict(dna: dict[str, float], dest: Destination, travel_type: str, tier: str, month: int | None,
            days: int) -> Suitability:
    model = _model()
    f = featurize(dna, dest, travel_type, tier, month, days)
    x = pd.DataFrame([f])[FEATURES]
    prob = float(model.predict_proba(x)[0, 1])

    # Counterfactual explanation per factor group
    factors = []
    neutral = featurize({d: 0.5 for d in DIMENSIONS}, dest, travel_type, tier, month, days)
    for group, cols in GROUPS.items():
        alt = dict(f)
        for c in cols:
            if group == "preference fit":
                alt[c] = neutral[c]
            elif c == "budget_ord":
                alt[c] = 1.0
            elif _NEUTRAL.get(c) is not None:
                alt[c] = _NEUTRAL[c]
        p_alt = float(model.predict_proba(pd.DataFrame([alt])[FEATURES])[0, 1])
        delta = prob - p_alt
        factors.append({"factor": group, "impact": round(delta, 3),
                        "direction": "helps" if delta > 0.01 else ("hurts" if delta < -0.01 else "neutral")})
    factors.sort(key=lambda d: abs(d["impact"]), reverse=True)
    label = "excellent fit" if prob >= 0.8 else "good fit" if prob >= 0.6 else "risky" if prob >= 0.4 else "poor fit"
    return Suitability(dest.name, round(prob, 3), label, factors)
