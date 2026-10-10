"""Budget and duration feasibility analysis (deterministic, auditable arithmetic)."""
from __future__ import annotations

from src.config import BUDGET_TIERS
from src.services.catalog import Catalog, Destination

BUFFER = 0.10  # contingency added on top of estimated costs
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def cost_breakdown(dest: Destination, days: int, travelers: int, tier: str, origin_region: str | None,
                   activities_cost_pp: float | None = None) -> dict:
    stay = dest.daily_cost[tier] * days * travelers
    if activities_cost_pp is None:  # typical: ~1.5 paid activities per day at the destination's median price
        prices = sorted(a.cost for a in dest.activities)
        activities_cost_pp = prices[len(prices) // 2] * 1.5 * days
    activities = activities_cost_pp * travelers
    flight_pp = Catalog.flight_estimate(origin_region, dest.region)
    flights = flight_pp * travelers if flight_pp is not None else 0.0
    subtotal = stay + activities + flights
    return {"tier": tier, "stay_food_local": round(stay), "activities": round(activities), "flights": round(flights),
            "flights_included": flight_pp is not None, "contingency": round(subtotal * BUFFER),
            "total": round(subtotal * (1 + BUFFER))}


def analyze(dest: Destination, days: int, travelers: int, tier: str, budget_usd: float | None,
            origin_region: str | None, month: int | None, activities_cost_pp: float | None = None) -> dict:
    est = cost_breakdown(dest, days, travelers, tier, origin_region, activities_cost_pp)
    by_tier = {t: cost_breakdown(dest, days, travelers, t, origin_region, activities_cost_pp)["total"] for t in BUDGET_TIERS}
    notes: list[str] = []

    # ---- budget
    if budget_usd:
        ratio = est["total"] / budget_usd
        budget_status = "feasible" if ratio <= 0.95 else "tight" if ratio <= 1.1 else "over_budget"
        affordable = [t for t in BUDGET_TIERS if by_tier[t] <= budget_usd * 1.02]
        recommended_tier = affordable[-1] if affordable else None
        fixed = est["flights"] * (1 + BUFFER)
        per_day = (dest.daily_cost[tier] * travelers + (est["activities"] / max(days, 1))) * (1 + BUFFER)
        max_days = int(max(0, (budget_usd - fixed) // per_day)) if per_day else None
        if budget_status == "over_budget":
            notes.append(f"Estimated ${est['total']:,} exceeds the ${budget_usd:,.0f} budget by "
                         f"{(ratio - 1) * 100:.0f}%.")
            if recommended_tier and recommended_tier != tier:
                notes.append(f"Switching to {recommended_tier}-tier stays brings it to ${by_tier[recommended_tier]:,}.")
            elif not recommended_tier:
                notes.append("Even budget-tier travel does not fit; consider a cheaper destination or fewer days.")
        elif budget_status == "tight":
            notes.append("Budget is tight - keep a contingency and pre-book key activities.")
        else:
            notes.append(f"Comfortably within budget (≈{ratio * 100:.0f}% used).")
    else:
        ratio, budget_status, recommended_tier, max_days = None, "unknown", tier, None
        notes.append("No budget given - estimate shown for reference.")

    # ---- duration
    if days < dest.min_days:
        duration_status = "too_short"
        notes.append(f"{days} days is short for {dest.name}; at least {dest.min_days} recommended (ideal {dest.ideal_days}).")
    elif days > dest.max_days:
        duration_status = "too_long"
        notes.append(f"{days} days is long for {dest.name} alone; consider combining with a nearby destination.")
    else:
        duration_status = "good"
    flight_pp = Catalog.flight_estimate(origin_region, dest.region)
    if flight_pp and flight_pp >= 900 and days <= 4:
        notes.append("Long-haul flights will consume ~2 of these days; the trip may feel rushed.")

    # ---- season
    in_season = dest.in_season(month)
    if in_season is False:
        best = ", ".join(_MONTHS[m - 1] for m in dest.best_months)
        notes.append(f"{_MONTHS[month - 1]} is outside the best season for {dest.name} (best: {best}).")

    score = 1.0
    score -= {"feasible": 0, "tight": 0.2, "over_budget": 0.5, "unknown": 0.1}[budget_status]
    score -= {"good": 0, "too_short": 0.25, "too_long": 0.1}[duration_status]
    score -= 0.2 if in_season is False else 0
    return {"destination": dest.name, "estimate": est, "cost_by_tier": by_tier, "budget_usd": budget_usd,
            "budget_utilization": round(ratio, 3) if ratio else None, "budget_status": budget_status,
            "recommended_tier": recommended_tier, "max_affordable_days": max_days,
            "duration_status": duration_status, "in_season": in_season, "feasibility_score": round(max(score, 0.0), 2),
            "notes": notes}
