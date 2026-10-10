"""Input guardrails. Deterministic on purpose: they run before any LLM sees the text, are fast,
and cannot themselves be prompt-injected."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_LEN, MAX_LEN = 3, 2000

_INJECTION = [
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|rules)",
    r"disregard\s+(the\s+|all\s+)?(previous|above|system)",
    r"(reveal|show|print|repeat)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions)",
    r"\byou\s+are\s+now\b", r"\bact\s+as\s+(an?\s+)?(unfiltered|jailbroken|dan)\b", r"\bjailbreak\b",
    r"\bDAN\s+mode\b", r"developer\s+mode", r"<\s*/?\s*(system|script|iframe)\b", r"\bsystem\s*:\s",
    r"override\s+(your|the)\s+(rules|guardrails|safety)",
]
_HARMFUL = [
    r"\bsmuggl\w*", r"\bfake\s+(passport|visa|id)\b", r"\bforged?\s+(passport|visa|documents?)\b",
    r"\b(buy|score|get)\s+(drugs|cocaine|heroin|meth)\b", r"\bhuman\s+trafficking\b", r"\bsex\s+tourism\b",
    r"\b(evade|avoid|bypass)\s+(customs|immigration|border\s+control)\b", r"\boverstay\s+(my\s+)?visa\s+illegally\b",
    r"\b(weapon|gun|explosive)s?\s+(through|past)\s+(security|customs)\b",
]
_PII = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "card_number": r"\b(?:\d[ -]?){13,16}\b",
    "phone": r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)",
    "passport": r"\b[A-Z]{1,2}\d{7}\b",
}
_TRAVEL_TERMS = set("""trip travel travelling traveling traveler traveller holiday holidays vacation vacations tour tourist
itinerary itineraries destination destinations visit visiting beach beaches resort resorts hotel hotels hostel stay
flight flights fly honeymoon getaway backpack backpacking sightseeing sightsee museum museums temple temples food foodie
cuisine nightlife party hike hiking trek trekking nature island islands city cities country mountains adventure spa
budget days day week weeks weekend family kids couple solo friends cruise safari snorkel snorkelling diving surf
culture cultural heritage shopping explore exploring abroad europe asia africa america beachside rated ratings reviews
review recommend recommendation activities activity compare plan planning accommodation
lights northern aurora volcano volcanoes springs waterfall waterfalls scenic wildlife snow ski skiing desert hostels
backpacker backpackers romantic quiet relaxing relax market markets street theme zoo zoos aquarium lake lakes sunset
sunrise views airport airline airlines""".split())


@dataclass
class GuardrailResult:
    allowed: bool
    sanitized_query: str
    reasons: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    category: str = "ok"  # ok | empty | too_long | injection | harmful | off_topic

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def redact_pii(text: str) -> tuple[str, list[str]]:
    found = []
    for label, pat in _PII.items():
        if re.search(pat, text):
            found.append(label)
            text = re.sub(pat, f"[{label.upper()} REDACTED]", text)
    return text, found


def check_query(query: str | None, known_destinations: list[str] | None = None) -> GuardrailResult:
    q = (query or "").strip()
    if len(q) < MIN_LEN:
        return GuardrailResult(False, q, ["Query is empty or too short. Describe the trip you want to plan."], category="empty")
    if len(q) > MAX_LEN:
        return GuardrailResult(False, q[:MAX_LEN], [f"Query exceeds {MAX_LEN} characters."], category="too_long")

    q = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", q)  # strip control characters
    low = q.lower()
    for pat in _INJECTION:
        if re.search(pat, low, flags=re.IGNORECASE):
            return GuardrailResult(False, q, ["Possible prompt-injection attempt detected; request blocked."],
                                   category="injection")
    for pat in _HARMFUL:
        if re.search(pat, low):
            return GuardrailResult(False, q, ["Request involves illegal or unsafe activity; WanderVision only assists "
                                              "with lawful travel planning."], category="harmful")

    # Destination names count as travel signal before redaction so "Rio 2025" is not mistaken for PII.
    tokens = set(re.findall(r"[a-z]+", low))
    dest_hit = any(d.lower() in low for d in (known_destinations or []))
    has_number_days = bool(re.search(r"\b\d+\s*-?\s*(day|days|night|nights|week|weeks)\b", low))
    if not (tokens & _TRAVEL_TERMS or dest_hit or has_number_days):
        return GuardrailResult(False, q, ["This assistant only handles travel planning questions "
                                          "(destinations, itineraries, budgets, activities)."], category="off_topic")

    sanitized, redactions = redact_pii(q)
    warnings = [f"Removed personal data from the query: {', '.join(redactions)}."] if redactions else []
    return GuardrailResult(True, sanitized, redactions=redactions, warnings=warnings)


def check_numbers(budget: float | None, days: int | None, travelers: int | None) -> list[str]:
    """Sanity checks for structured parameters; returns blocking problems."""
    problems = []
    if budget is not None and budget <= 0:
        problems.append("Budget must be positive.")
    if budget is not None and budget > 5_000_000:
        problems.append("Budget looks unrealistic (> $5M).")
    if days is not None and not 1 <= days <= 60:
        problems.append("Trip duration must be between 1 and 60 days.")
    if travelers is not None and not 1 <= travelers <= 30:
        problems.append("Number of travelers must be between 1 and 30.")
    return problems
