"""One-shot bootstrap: dataset -> vector index -> suitability model (about 4-6 minutes on a laptop CPU)."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for step in ("build_dataset.py", "build_index.py", "train_model.py"):
    print(f"\n=== {step} ===", flush=True)
    subprocess.run([sys.executable, str(HERE / step)], check=True)
print("\nAll artifacts built. Start the API with:  uvicorn src.main:app --reload")
