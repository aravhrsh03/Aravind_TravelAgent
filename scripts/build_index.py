"""Step 2 of the pipeline: corpus -> chunks -> embeddings -> ChromaDB."""
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402
from src.rag import vector_store  # noqa: E402
from src.rag.corpus import get_corpus  # noqa: E402


def main() -> None:
    s = get_settings()
    if s.chroma_dir.exists():
        shutil.rmtree(s.chroma_dir)
    t0 = time.time()
    corpus = get_corpus()
    vector_store.upsert(corpus.ids, corpus.docs, corpus.metas)
    print(f"indexed {vector_store.get_collection().count()} chunks in {time.time() - t0:.1f}s -> {s.chroma_dir}")


if __name__ == "__main__":
    main()
