"""Step 1 of the pipeline: raw UCI ratings -> cleaned travel-experience corpus + traveler profiles."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402
from src.services.dataset_builder import build_corpus, clean  # noqa: E402


def main() -> None:
    s = get_settings()
    s.processed_dir.mkdir(parents=True, exist_ok=True)
    users, df = build_corpus()
    df = clean(df)
    users.to_csv(s.travelers_path, index=False)
    df.to_csv(s.experiences_path, index=False)
    df.sample(200, random_state=7).to_csv(s.data_dir / "sample_data" / "travel_experiences_sample.csv", index=False)
    print(f"travelers: {len(users)}  experiences: {len(df)}")
    print(df["rating"].value_counts().sort_index().to_string())
    print(df.groupby("destination")["rating"].agg(["count", "mean"]).sort_values("count", ascending=False).head(10).round(2))


if __name__ == "__main__":
    main()
