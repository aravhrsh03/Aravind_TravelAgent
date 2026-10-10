"""Deterministic extraction of trip parameters and preference signals from free text."""
from __future__ import annotations

import re

from src.config import DIMENSIONS

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
_MONTH_ABBR = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
_FX_TO_USD = {"usd": 1.0, "$": 1.0, "dollars": 1.0, "eur": 1.08, "€": 1.08, "euros": 1.08, "gbp": 1.27,
              "£": 1.27, "pounds": 1.27, "inr": 0.012, "₹": 0.012, "rs": 0.012, "rupees": 0.012, "aed": 0.27,
              "sgd": 0.74, "aud": 0.66, "jpy": 0.0067, "¥": 0.0067}
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "a": 1, "couple of": 2, "few": 3}

# Lexicon: phrase -> weight per dimension. Used by the offline preference classifier.
LEXICON: dict[str, list[str]] = {
    "beach": ["beach", "beaches", "sea", "ocean", "island", "snorkel", "snorkelling", "snorkeling", "diving", "surf",
              "surfing", "coast", "coastal", "sand", "lagoon", "tropical", "swim", "swimming", "reef", "seaside"],
    "culture": ["culture", "cultural", "sightseeing", "sightsee", "history", "historic", "historical", "museum",
                "museums", "temple", "temples", "heritage", "architecture", "art", "gallery", "palace", "fort",
                "ruins", "monument", "monuments", "church", "cathedral", "theatre", "theater", "landmark", "landmarks"],
    "food": ["food", "foodie", "cuisine", "local food", "street food", "eat", "eating", "restaurant", "restaurants",
             "culinary", "cooking", "wine", "tasting", "dining", "gastronomy", "cafe", "cafes", "market"],
    "nightlife": ["nightlife", "party", "parties", "club", "clubs", "clubbing", "bar", "bars", "pub", "pubs",
                  "night out", "drinks", "cocktail", "live music", "dance", "festival"],
    "nature": ["nature", "hike", "hiking", "trek", "trekking", "mountain", "mountains", "national park", "wildlife",
               "waterfall", "scenery", "scenic", "outdoors", "outdoor", "adventure", "lake", "forest", "volcano",
               "glacier", "northern lights", "safari", "camping", "views", "paragliding", "bungy", "kayak"],
    "shopping": ["shopping", "shop", "shops", "mall", "malls", "souk", "souvenir", "souvenirs", "bazaar",
                 "boutique", "fashion", "markets", "luxury brands"],
    "wellness": ["wellness", "spa", "spas", "relax", "relaxing", "relaxation", "massage", "yoga", "ayurveda",
                 "retreat", "peaceful", "quiet", "resort", "honeymoon", "romantic", "unwind", "detox", "hot spring"],
    "family": ["family", "kids", "kid", "children", "child", "toddler", "zoo", "theme park", "amusement",
               "disney", "aquarium", "family-friendly", "kid-friendly", "parents", "grandparents"],
}
_TRAVEL_TYPE_CUES = {
    "family": ["family", "kids", "children", "my son", "my daughter", "toddler", "parents"],
    "couple": ["couple", "honeymoon", "partner", "wife", "husband", "girlfriend", "boyfriend", "anniversary", "romantic"],
    "friends": ["friends", "group of", "buddies", "bachelor", "bachelorette", "squad", "gang"],
    "business": ["business", "conference", "work trip", "client meeting"],
    "solo": ["solo", "alone", "by myself", "on my own", "backpack"],
}
_ORIGIN_CUES = {
    "South Asia": ["from india", "from mumbai", "from delhi", "from bangalore", "from bengaluru", "from chennai",
                   "from hyderabad", "from kolkata", "from pune", "from sri lanka", "from pakistan", "from bangladesh"],
    "Europe": ["from london", "from uk", "from paris", "from berlin", "from germany", "from france", "from europe",
               "from madrid", "from rome", "from amsterdam"],
    "North America": ["from the us", "from usa", "from new york", "from california", "from canada", "from toronto",
                      "from chicago", "from america", "from los angeles"],
    "Southeast Asia": ["from singapore", "from malaysia", "from bangkok", "from jakarta", "from manila", "from vietnam"],
    "Middle East": ["from dubai", "from uae", "from qatar", "from saudi", "from doha", "from abu dhabi"],
    "East Asia": ["from japan", "from tokyo", "from china", "from korea", "from seoul", "from hong kong"],
    "Oceania": ["from australia", "from sydney", "from melbourne", "from new zealand", "from auckland"],
    "Latin America": ["from brazil", "from mexico", "from argentina", "from chile", "from peru", "from colombia"],
    "Africa": ["from south africa", "from kenya", "from nigeria", "from egypt", "from morocco"],
}


# "for two" / "a weekend for two", but not "for two weeks"
_FOR_TWO = re.compile(r"\bfor\s+(?:two|2)\b(?!\s*-?\s*(?:day|days|night|nights|week|weeks|month|months|hours?))")


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def extract_days(text: str) -> int | None:
    low = text.lower()
    m = re.search(r"(\d+)\s+(?:free|full|whole|spare|extra|available|clear)\s+days?\b", low)  # "3 free days"
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*-?\s*(?:day|days|d)\b", low)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*-?\s*nights?\b", low)
    if m:
        return int(m.group(1)) + 1
    m = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s*-?\s*nights?\b", low)  # "seven nights"
    if m:
        return _WORD_NUM[m.group(1)] + 1
    m = re.search(r"(\d+|a|one|two|three|four)\s*-?\s*weeks?\b", low)
    if m:
        n = m.group(1)
        return 7 * (int(n) if n.isdigit() else _WORD_NUM.get(n, 1))
    if "weekend" in low:
        return 2
    m = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s*-?\s*days?\b", low)
    return _WORD_NUM[m.group(1)] if m else None


def extract_budget(text: str) -> float | None:
    """Total budget in USD, from forms like '$2,000', '2000 usd', '₹1,50,000', '1.5 lakh', '3k euros'."""
    low = text.lower().replace(" ", " ")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|lac)\b", low)
    if m:
        return round(float(m.group(1)) * 100_000 * _FX_TO_USD["inr"], 2)
    pat_pre = r"(\$|€|£|₹|¥|usd|eur|gbp|inr|rs\.?|aed|sgd|aud)\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?"
    pat_post = r"(\d[\d,]*(?:\.\d+)?)\s*(k)?\s*(usd|dollars|eur|euros|gbp|pounds|inr|rupees|aed|sgd|aud|jpy|\$|€|£)"
    m = re.search(pat_pre, low)
    if m:
        cur = m.group(1).rstrip(".")
        amount = _num(m.group(2)) * (1000 if m.group(3) else 1)
        return round(amount * _FX_TO_USD.get(cur, 1.0), 2)
    m = re.search(pat_post, low)
    if m:
        amount = _num(m.group(1)) * (1000 if m.group(2) else 1)
        return round(amount * _FX_TO_USD.get(m.group(3), 1.0), 2)
    m = re.search(r"budget\s*(?:of|is|around|about|:)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?", low)
    if m:
        return round(_num(m.group(1)) * (1000 if m.group(2) else 1), 2)
    return None


def extract_budget_tier(text: str, budget_usd: float | None, days: int | None, travelers: int) -> str | None:
    low = text.lower()
    if re.search(r"\b(luxury|luxurious|5[- ]star|five[- ]star|splurge|premium|high[- ]end)\b", low):
        return "luxury"
    if re.search(r"\b(cheap|cheapest|on a budget|budget[- ](trip|travel|friendly|stay|hotel)s?|limited budget|"
                 r"tight budget|low budget|small budget|backpack\w*|affordable|low[- ]cost|economical|hostels?|"
                 r"shoestring)\b", low):
        return "budget"
    if re.search(r"\b(mid[- ]range|moderate|comfortable|3[- ]star|4[- ]star)\b", low):
        return "mid"
    if budget_usd and days:
        per_day = budget_usd / max(days, 1) / max(travelers, 1)
        # total budget usually also covers flights, so thresholds sit above the daily stay costs
        return "budget" if per_day < 120 else ("mid" if per_day < 420 else "luxury")
    return None


def extract_travelers(text: str, travel_type: str | None) -> int:
    low = text.lower()
    m = re.search(r"(\d+)\s*(?:people|persons|travell?ers|adults|of us|friends|pax|guests)", low)
    if m:
        n = int(m.group(1))
        kids = re.search(r"(\d+)\s*(?:kids|children|child)", low)
        return n + (int(kids.group(1)) if kids and "adult" in low else 0)
    m = re.search(r"family of (\d+)", low)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(two|three|four|five|six|seven|eight)\s+(?:people|persons|adults|travell?ers|of us)\b", low)
    if m:
        return _WORD_NUM[m.group(1)] if m.group(1) in _WORD_NUM else {"five": 5, "six": 6, "seven": 7, "eight": 8}[m.group(1)]
    if _FOR_TWO.search(low):
        return 2
    m = re.search(r"(\d+)\s*(?:kids|children)", low)
    if m:
        return 2 + int(m.group(1))
    return {"couple": 2, "family": 4, "friends": 4}.get(travel_type or "", 1)


def extract_month(text: str) -> int | None:
    low = text.lower()
    for i, m in enumerate(MONTHS):
        if re.search(rf"\b{m}\b", low):
            return i + 1
    for abbr, i in _MONTH_ABBR.items():
        if abbr != "may" and re.search(rf"\b{abbr}\b", low):
            return i
    seasons = {"summer": 7, "winter": 12, "spring": 4, "autumn": 10, "fall": 10, "christmas": 12, "diwali": 11,
               "new year": 12, "monsoon": 7}
    for k, v in seasons.items():
        if re.search(rf"\b{k}\b", low):  # whole words only: "hot springs" and "waterfalls" are not seasons
            return v
    return None


def extract_travel_type(text: str) -> str | None:
    low = text.lower()
    scores = {t: sum(1 for c in cues if c in low) for t, cues in _TRAVEL_TYPE_CUES.items()}
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    if _FOR_TWO.search(low) or re.search(r"\btwo\s+(?:people|adults|of us)\b", low):
        return "couple"  # "a weekend for two", "two people who love temples"
    return None


def extract_origin(text: str) -> str | None:
    low = text.lower()
    for region, cues in _ORIGIN_CUES.items():
        if any(c in low for c in cues):
            return region
    for region in _ORIGIN_CUES:  # a region named directly: "flying from Oceania", "from North America"
        if re.search(rf"\bfrom\s+(?:the\s+)?{region.lower()}\b", low):
            return region
    return None


_DEST_REGIONS = {
    "europe": ["Europe"], "european": ["Europe"],
    "southeast asia": ["Southeast Asia"], "south east asia": ["Southeast Asia"], "east asia": ["East Asia"],
    "south asia": ["South Asia"], "asia": ["South Asia", "Southeast Asia", "East Asia"],
    "middle east": ["Middle East"], "africa": ["Africa"], "north america": ["North America"],
    "usa": ["North America"], "the us": ["North America"], "america": ["North America", "Latin America"],
    "latin america": ["Latin America"], "south america": ["Latin America"], "caribbean": ["Latin America"],
    "oceania": ["Oceania"], "australia": ["Oceania"], "new zealand": ["Oceania"],
}


def extract_destination_regions(text: str) -> list[str]:
    """Regions the traveler wants to VISIT ("in Europe", "to Southeast Asia"), not where they fly from."""
    low = text.lower()
    for key in sorted(_DEST_REGIONS, key=len, reverse=True):  # longest first: "southeast asia" before "asia"
        if re.search(rf"\b(in|to|around|across|within|visit|visiting|explore|exploring|tour of|trip to)\s+(the\s+)?{key}\b", low) \
                and not re.search(rf"\bfrom\s+(the\s+)?{key}\b", low):
            return _DEST_REGIONS[key]
    return []


def lexicon_dna(text: str) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Score each dimension 0-1 from keyword evidence. Unmentioned dimensions sit at a 0.2 prior."""
    low = text.lower()
    evidence: dict[str, list[str]] = {d: [] for d in DIMENSIONS}
    for dim, words in LEXICON.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", low):
                evidence[dim].append(w)
    dna = {}
    for d in DIMENSIONS:
        hits = len(set(evidence[d]))
        dna[d] = round(min(1.0, 0.3 + 0.35 * hits) if hits else 0.2, 3)
    # Negations: "no nightlife", "not into museums", "avoid crowds/party"
    for d, words in LEXICON.items():
        for w in words:
            if re.search(rf"\b(no|not into|avoid|hate|without|don't like|dont like)\s+(the\s+)?{re.escape(w)}\b", low):
                dna[d] = 0.05
                evidence[d] = [f"NOT {w}"]
    return dna, {d: v for d, v in evidence.items() if v}
