import os
import sys
import tempfile
from pathlib import Path

# Isolate test feedback from the real learning loop (must run before src.config is imported).
os.environ.setdefault("FEEDBACK_DB", str(Path(tempfile.mkdtemp()) / "test_feedback.db"))
os.environ.setdefault("LLM_PROVIDER", "offline")  # deterministic, free, no network in tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
