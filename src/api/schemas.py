"""Request/response models. Field constraints are the first layer of input validation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.config import DIMENSIONS

TravelType = Literal["solo", "couple", "family", "friends", "business"]
Tier = Literal["budget", "mid", "luxury"]
Region = Literal["South Asia", "Southeast Asia", "East Asia", "Middle East", "Europe", "Africa", "North America",
                 "Latin America", "Oceania"]


class Filters(BaseModel):
    destinations: list[str] | None = None
    travel_types: list[TravelType] | None = None
    budget_tiers: list[Tier] | None = None
    regions: list[str] | None = None
    categories: list[str] | None = None
    min_rating: int | None = Field(None, ge=1, le=5)
    max_spend_per_day: float | None = Field(None, gt=0)
    months: list[int] | None = None
    min_days: int | None = Field(None, ge=1, le=60)
    max_days: int | None = Field(None, ge=1, le=60)

    @field_validator("months")
    @classmethod
    def _months(cls, v):
        if v and any(not 1 <= m <= 12 for m in v):
            raise ValueError("months must be 1-12")
        return v


class TripParams(BaseModel):
    """Optional structured overrides; anything omitted is inferred from the query."""
    days: int | None = Field(None, ge=1, le=60)
    budget_usd: float | None = Field(None, gt=0, le=5_000_000)
    travelers: int | None = Field(None, ge=1, le=30)
    travel_type: TravelType | None = None
    budget_tier: Tier | None = None
    month: int | None = Field(None, ge=1, le=12)
    origin_region: Region | None = None
    destinations: list[str] | None = None
    regions: list[Region] | None = Field(None, description="Restrict recommendations to these regions")
    dna: dict[str, float] | None = Field(None, description=f"Optional preference sliders 0-1 for {DIMENSIONS}")

    @field_validator("dna")
    @classmethod
    def _dna(cls, v):
        if v:
            bad = [k for k, x in v.items() if k not in DIMENSIONS or not 0 <= x <= 1]
            if bad:
                raise ValueError(f"invalid DNA keys/values: {bad}")
        return v


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000, examples=[
        "A couple wants a 5-day trip focused on beaches, sightseeing and local food in December, budget $3000"])
    params: TripParams = Field(default_factory=TripParams)


class SearchRequest(QueryRequest):
    filters: Filters = Field(default_factory=Filters)
    top_k: int = Field(10, ge=1, le=50)
    mode: Literal["hybrid", "dense", "keyword"] = "hybrid"
    personalize: bool = Field(True, description="Use the inferred Traveler DNA in prioritization")


class FeasibilityRequest(BaseModel):
    destination: str
    days: int = Field(..., ge=1, le=60)
    travelers: int = Field(1, ge=1, le=30)
    budget_tier: Tier = "mid"
    budget_usd: float | None = Field(None, gt=0)
    origin_region: Region | None = None
    month: int | None = Field(None, ge=1, le=12)


class SuitabilityRequest(BaseModel):
    destination: str
    query: str | None = Field(None, max_length=2000, description="Used to infer DNA if `dna` is not given")
    dna: dict[str, float] | None = None
    travel_type: TravelType = "couple"
    budget_tier: Tier = "mid"
    month: int | None = Field(None, ge=1, le=12)
    days: int = Field(5, ge=1, le=60)


class CompareRequest(BaseModel):
    destinations: list[str] = Field(..., min_length=2, max_length=2)
    query: str | None = Field(None, max_length=2000)
    dna: dict[str, float] | None = None
    travel_type: TravelType | None = None


class TwinsRequest(BaseModel):
    query: str | None = Field(None, max_length=2000)
    dna: dict[str, float] | None = None
    k: int = Field(10, ge=1, le=100)


class FeedbackRequest(BaseModel):
    request_id: str | None = None
    destination: str
    rating: int = Field(..., ge=1, le=5)
    helpful: bool | None = None
    comment: str | None = Field(None, max_length=1000)
    travel_type: TravelType | None = None
