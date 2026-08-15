from __future__ import annotations

import logging
from typing import Any

from app.ingestion.embedder import embed_texts
from app.vectorstore.chroma_client import get_bot_sensor_collection

logger = logging.getLogger(__name__)


def search_bot_sensor_data(
    query_text: str,
    machine_id: str | None = None,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Semantic search against the dedicated bot_sensor_data collection."""
    if not query_text or not query_text.strip():
        return []

    collection = get_bot_sensor_collection()
    if collection.count() == 0:
        return []

    try:
        embedding = embed_texts([query_text])[0]
    except Exception:
        logger.exception("search_bot_sensor_data: failed to embed query text")
        return []

    where_filter = {"machine_id": str(machine_id)} if machine_id else None
    n_results = max(1, min(k, collection.count()))

    try:
        results = collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where_filter,
        )
    except Exception:
        logger.exception("search_bot_sensor_data: query failed")
        return []

    docs = results.get("documents", [[]])[0] if results.get("documents") else []
    metas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
    distances = results.get("distances", [[]])[0] if results.get("distances") else []

    items = []
    for doc, meta, dist in zip(docs, metas, distances):
        items.append({
            "content": doc,
            "metadata": meta or {},
            "similarity": round(1.0 - float(dist), 4) if dist is not None else 0.0,
        })
    return items
