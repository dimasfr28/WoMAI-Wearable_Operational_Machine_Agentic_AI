"""MiniLM multilingual embedding — Section 6.5."""
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    # normalize_embeddings=True supaya cosine similarity langsung konsisten dengan
    # hnsw:space="cosine" di Chroma.
    return model.encode(texts, normalize_embeddings=True).tolist()
