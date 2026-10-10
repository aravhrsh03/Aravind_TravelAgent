"""Step 3 of the pipeline: train the itinerary suitability predictor."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.suitability_model import train  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(train(), indent=2))
