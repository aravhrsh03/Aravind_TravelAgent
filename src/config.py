"""Central configuration. Every tunable lives here and can be overridden by env vars / .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("USE_TF", "0")  # keep transformers from importing TensorFlow
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")  # chroma telemetry off
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))
load_dotenv(ROOT / ".env")  # exposes ANTHROPIC_API_KEY etc. to the SDK, which reads os.environ

# Preference dimensions used everywhere ("Traveler DNA").
DIMENSIONS: list[str] = [
    "beach", "culture", "food", "nightlife", "nature", "shopping", "wellness", "family",
]
TRAVEL_TYPES: list[str] = ["solo", "couple", "family", "friends", "business"]
BUDGET_TIERS: list[str] = ["budget", "mid", "luxury"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: str = "auto"  # auto | anthropic | offline
    llm_model: str = "claude-opus-5-5"
    llm_timeout_s: float = 90.0

    # Retrieval
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    use_reranker: bool = True
    collection_name: str = "travel_experiences"
    rrf_k: int = 60
    candidate_pool: int = 50  # per retriever, before fusion
    default_top_k: int = 10

    # Prioritization weights (relevance, rating, preference match, feedback)
    w_relevance: float = 0.45
    w_rating: float = 0.25
    w_preference: float = 0.20
    w_feedback: float = 0.10

    # Planning loop
    judge_pass_threshold: float = 3.5  # mean rubric score (1-5) required to accept a plan
    max_revisions: int = 1

    # Paths
    data_dir: Path = ROOT / "data"
    raw_dir: Path = ROOT / "data" / "raw"
    processed_dir: Path = ROOT / "data" / "processed"
    catalog_path: Path = ROOT / "data" / "catalog" / "destinations.json"
    experiences_path: Path = ROOT / "data" / "processed" / "travel_experiences.csv"
    travelers_path: Path = ROOT / "data" / "processed" / "traveler_profiles.csv"
    chroma_dir: Path = ROOT / "data" / "processed" / "chroma"
    model_path: Path = ROOT / "data" / "processed" / "suitability_model.joblib"
    feedback_db: Path = ROOT / "data" / "processed" / "feedback.db"

    # API
    api_url: str = "http://127.0.0.1:8000"

    @property
    def resolved_provider(self) -> str:
        if self.llm_provider != "auto":
            return self.llm_provider
        has_creds = any(os.getenv(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"))
        return "anthropic" if has_creds else "offline"


@lru_cache
def get_settings() -> Settings:
    return Settings()
