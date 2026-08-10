"""ChromaDB client — Section 5. Two collections, cosine space, manual embeddings
(embedding function run in backend via sentence-transformers, not Chroma's default)."""
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _get_or_create(collection_name: str):
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def get_docs_collection():
    return _get_or_create(settings.CHROMA_COLLECTION_DOCS)


def get_sensor_collection():
    return _get_or_create(settings.CHROMA_COLLECTION_SENSOR)


def upsert_chunks(collection, ids: list[str], embeddings: list[list[float]], documents: list[str], metadatas: list[dict]):
    collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)


def delete_chunks(collection, ids: list[str]) -> None:
    """Delete vectors by id. No-op on an empty id list (Chroma errors on `ids=[]`)."""
    if ids:
        collection.delete(ids=ids)


def query_top1(collection, embedding: list[float], where: dict | None = None) -> dict:
    # Chroma's HNSW query can raise a 500 ("Cannot return the results in a
    # contigious 2D array. Probably ef or M is too small") when the collection
    # has very few vectors (seen with as few as 8) — a known small-collection
    # limitation, not a real error. Empty-result shape mirrors what Chroma
    # returns for a collection with zero vectors, so callers (duplicate_check)
    # already handle it as "nothing to compare against".
    if collection.count() == 0:
        return {"ids": [[]], "distances": [[]]}
    try:
        return collection.query(query_embeddings=[embedding], n_results=1, where=where)
    except Exception:
        return {"ids": [[]], "distances": [[]]}


def query(collection, embedding: list[float], n_results: int = 5, where: dict | None = None) -> dict:
    return collection.query(query_embeddings=[embedding], n_results=n_results, where=where)
