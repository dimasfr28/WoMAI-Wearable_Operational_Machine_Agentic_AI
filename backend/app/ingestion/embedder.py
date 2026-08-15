"""MiniLM multilingual embedding client — Section 6.5.

Calls the standalone `embedding-service` container over HTTP instead of
loading sentence-transformers/torch in-process. This split exists so
day-to-day backend code changes stop invalidating the Docker layer cache for
the embedding model download, and the backend image no longer needs a torch
install of its own just for this.
"""
import httpx

from app.config import settings

# Generous timeout: embedding a full PDF's worth of chunks (duplicate_check.py,
# upload_pdf) can be dozens of texts in one call; the model itself is small
# (MiniLM) so this is mostly headroom for a cold container, not per-call cost.
_TIMEOUT = httpx.Timeout(connect=10, read=120, write=60, pool=30)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = httpx.post(
        f"{settings.EMBEDDING_SERVICE_URL}/embed",
        json={"texts": texts},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["embeddings"]
