"""Budget & duration feasibility agent: checks the top pick and negotiates adjustments."""
from __future__ import annotations

from src.agents.base import Agent, TripState
from src.services import feasibility as feas
from src.services.catalog import get_catalog


class FeasibilityAgent(Agent):
    name = "FeasibilityAnalyst"
    role = "Checks budget and trip length; adjusts tier, days or destination when the plan doesn't fit"

    def act(self, state: TripState) -> tuple[str, dict]:
        prof, cat = state.profile, get_catalog()
        if not state.candidates:
            state.feasibility = None
            return "No candidate to analyze", {}
        fb = state.revision_feedback or {}
        chosen = state.candidates[0]
        tier, days = fb.get("tier") or prof["budget_tier"], prof["days"]
        adjustments: list[str] = []

        fz = feas.analyze(cat.get(chosen["destination"]), days, prof["travelers"], tier, prof["budget_usd"],
                          prof["origin_region"], prof["month"])
        if fz["budget_status"] == "over_budget":
            if fz["recommended_tier"] and fz["recommended_tier"] != tier:
                adjustments.append(f"Downgraded stays from {tier} to {fz['recommended_tier']} tier to fit the budget.")
                tier = fz["recommended_tier"]
            elif not prof["destinations"]:  # user didn't insist on a destination -> try affordable alternatives
                for alt in state.candidates[1:]:
                    afz = feas.analyze(cat.get(alt["destination"]), days, prof["travelers"], tier, prof["budget_usd"],
                                       prof["origin_region"], prof["month"])
                    alt_tier = afz["recommended_tier"]
                    if afz["budget_status"] in ("feasible", "tight") or alt_tier:
                        adjustments.append(f"{chosen['destination']} does not fit the budget at any tier; switched to "
                                           f"{alt['destination']} (next best match that fits).")
                        chosen, tier = alt, (tier if afz["budget_status"] in ("feasible", "tight") else alt_tier)
                        break
            if fz["budget_status"] == "over_budget" and not adjustments and fz["max_affordable_days"]:
                new_days = max(2, fz["max_affordable_days"])
                if new_days < days:
                    adjustments.append(f"Shortened the trip from {days} to {new_days} days to fit the budget.")
                    days = new_days
            fz = feas.analyze(cat.get(chosen["destination"]), days, prof["travelers"], tier, prof["budget_usd"],
                              prof["origin_region"], prof["month"])

        state.feasibility = {"destination": chosen["destination"], "tier": tier, "days": days,
                             "adjustments": adjustments, "analysis": fz}
        state.post(self.name, "ItineraryPlanner",
                   f"Plan {chosen['destination']} for {days} days at {tier} tier; budget {fz['budget_status']}"
                   + (f"; adjustments: {len(adjustments)}" if adjustments else ""))
        return (f"{chosen['destination']}: budget {fz['budget_status'].replace('_', ' ')}, duration {fz['duration_status']}",
                state.feasibility)
