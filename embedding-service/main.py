"""Standalone embedding microservice — wraps sentence-transformers behind HTTP so
the main backend image doesn't need torch/sentence-transformers baked in (that
pin used to force torch==2.6.0+cpu on the whole backend image just to satisfy
mineru[pipeline], and re-downloaded the ~500MB+ model on every backend rebuild).

Mirrors backend/app/ingestion/embedder.py's behavior exactly: same model name
default, same normalize_embeddings=True (required for cosine similarity to stay
consistent with Chroma's hnsw:space="cosine" collections), same lru_cache-once
model load.
"""
from __future__ import annotations

import os
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

app = FastAPI(title="Embedding Service", version="1.0.0")


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


@app.on_event("startup")
def _warm_up() -> None:
    # Load the model into memory at container startup rather than on the first
    # request — otherwise the first caller (a real PDF upload or sensor-run
    # close, not a health check) eats the multi-second model load latency.
    _get_model()


class EmbedIn(BaseModel):
    texts: list[str]


class EmbedOut(BaseModel):
    embeddings: list[list[float]]


@app.post("/embed", response_model=EmbedOut)
def embed(payload: EmbedIn):
    if not payload.texts:
        return EmbedOut(embeddings=[])
    model = _get_model()
    embeddings = model.encode(payload.texts, normalize_embeddings=True).tolist()
    return EmbedOut(embeddings=embeddings)


@app.get("/health")
def health():
    return {"status": "ok", "model": EMBEDDING_MODEL}
