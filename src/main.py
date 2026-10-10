"""FastAPI microservice entry point:  uvicorn src.main:app --reload"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("wandervision")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm every heavy component once so the first user request is fast."""
    t0 = time.time()
    from src.rag.corpus import get_corpus
    from src.rag.embeddings import embed, rerank_scores
    from src.rag.hybrid_retriever import hybrid_search
    from src.rag.vector_store import get_collection
    from src.services import learning
    from src.services.llm import get_llm
    from src.services.suitability_model import _model

    corpus = get_corpus()
    restored = learning.restore()
    embed(["warm up"])
    rerank_scores("warm up", ["warm up"])
    _model()
    hybrid_search("warm up beach trip", {"min_rating": 4}, top_k=3)  # loads the Chroma HNSW index + BM25 path
    log.info("WanderVision ready in %.1fs: %d chunks (BM25), %d vectors, %d learned experiences restored, LLM=%s",
             time.time() - t0, len(corpus.ids), get_collection().count(), restored, get_llm().status()["provider"])
    yield


app = FastAPI(
    title="WanderVision - AI Travel Planning & Itinerary Assistant",
    version="1.0.0",
    description="Hybrid-RAG retrieval of similar historical trips, multi-agent planning, suitability prediction, "
                "feasibility analysis, LLM-as-judge validation and a feedback loop.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_error", "detail": "Unexpected server error."})


@app.get("/health", tags=["ops"])
def health():
    from src.rag.corpus import get_corpus
    from src.rag.vector_store import get_collection
    from src.services.llm import get_llm

    s = get_settings()
    return {"status": "ok", "documents": len(get_corpus().ids), "vectors": get_collection().count(),
            "embedding_model": s.embedding_model, "reranker": s.reranker_model if s.use_reranker else None,
            "llm": get_llm().status()}
