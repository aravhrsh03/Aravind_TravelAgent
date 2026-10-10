"""Destination knowledge base: strengths, costs, seasons and costed activities."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from src.config import DIMENSIONS, get_settings

# Rough round-trip economy airfare (USD) between regions. Used only for feasibility estimates.
_REGIONS = ["South Asia", "Southeast Asia", "East Asia", "Middle East", "Europe",
            "Africa", "North America", "Latin America", "Oceania"]
_FLIGHT = np.array([
    #  SA   SEA   EA    ME    EU    AF    NA    LA    OC
    [150, 350, 650, 350, 750, 800, 1300, 1600, 1100],  # South Asia
    [350, 200, 450, 600, 900, 1000, 1300, 1700, 700],  # Southeast Asia
    [650, 450, 250, 800, 1000, 1200, 1100, 1600, 900],  # East Asia
    [350, 600, 800, 200, 500, 600, 1200, 1500, 1300],  # Middle East
    [750, 900, 1000, 500, 180, 700, 800, 1000, 1600],  # Europe
    [800, 1000, 1200, 600, 700, 400, 1300, 1300, 1500],  # Africa
    [1300, 1300, 1100, 1200, 800, 1300, 300, 600, 1400],  # North America
    [1600, 1700, 1600, 1500, 1000, 1300, 600, 400, 1600],  # Latin America
    [1100, 700, 900, 1300, 1600, 1500, 1400, 1600, 300],  # Oceania
])


@dataclass(frozen=True)
class Activity:
    name: str
    dimension: str
    cost: float
    hours: float


@dataclass
class Destination:
    name: str
    country: str
    region: str
    strengths: dict[str, float]
    daily_cost: dict[str, float]
    best_months: list[int]
    min_days: int
    ideal_days: int
    max_days: int
    summary: str
    activities: list[Activity] = field(default_factory=list)

    @property
    def vector(self) -> np.ndarray:
        return np.array([self.strengths[d] for d in DIMENSIONS], dtype=float)

    def in_season(self, month: int | None) -> bool | None:
        return None if month is None else month in self.best_months


class Catalog:
    def __init__(self, destinations: list[Destination]):
        self.destinations = destinations
        self._by_key = {d.name.lower(): d for d in destinations}

    def get(self, name: str | None) -> Destination | None:
        if not name:
            return None
        key = name.strip().lower()
        if key in self._by_key:
            return self._by_key[key]
        for d in self.destinations:  # lenient match: "machu picchu" -> Cusco is out of scope, but "rio" -> Rio de Janeiro works
            if key in d.name.lower() or d.name.lower() in key or key == d.country.lower():
                return d
        return None

    def names(self) -> list[str]:
        return [d.name for d in self.destinations]

    def find_mentions(self, text: str) -> list[Destination]:
        low = text.lower()
        aliases = {"rio": "Rio de Janeiro", "nyc": "New York", "machu picchu": "Cusco", "swiss alps": "Interlaken",
                   "switzerland": "Interlaken", "iceland": "Reykjavik", "ha long": "Hanoi", "halong": "Hanoi",
                   "disney world": "Orlando", "greece": "Santorini", "morocco": "Marrakech", "thailand": ["Phuket", "Bangkok"],
                   "japan": ["Tokyo", "Kyoto"], "italy": "Rome", "france": "Paris", "spain": "Barcelona", "portugal": "Lisbon",
                   "netherlands": "Amsterdam", "holland": "Amsterdam", "czech": "Prague", "turkey": "Istanbul",
                   "uae": "Dubai", "vietnam": "Hanoi", "australia": "Sydney", "new zealand": "Queenstown",
                   "south africa": "Cape Town", "brazil": "Rio de Janeiro", "peru": "Cusco", "mexico": "Cancun",
                   "england": "London", "united kingdom": "London", "britain": "London"}
        found: list[Destination] = []
        for d in self.destinations:
            if d.name.lower() in low:
                found.append(d)
        for alias, target in aliases.items():
            if alias in low:
                for name in ([target] if isinstance(target, str) else target):
                    dest = self._by_key[name.lower()]
                    if dest not in found:
                        found.append(dest)
        return found

    @staticmethod
    def flight_estimate(origin_region: str | None, dest_region: str) -> float | None:
        if not origin_region or origin_region not in _REGIONS:
            return None
        return float(_FLIGHT[_REGIONS.index(origin_region), _REGIONS.index(dest_region)])

    @staticmethod
    def regions() -> list[str]:
        return list(_REGIONS)


@lru_cache
def get_catalog() -> Catalog:
    raw = json.loads(get_settings().catalog_path.read_text(encoding="utf-8"))
    dests = []
    for d in raw["destinations"]:
        acts = [Activity(name=a[0], dimension=a[1], cost=float(a[2]), hours=float(a[3])) for a in d.pop("activities")]
        dests.append(Destination(**d, activities=acts))
    return Catalog(dests)
