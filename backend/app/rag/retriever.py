"""Retriever — wraps ChromaDB `knowledgebase_docs` collection for CRAG (Section 6.9).

Uses the backend's own embedder (paraphrase-multilingual-MiniLM-L12-v2) rather
than LangChain's Chroma wrapper's built-in embedding function, to stay
consistent with how chunks were originally embedded/upserted (Section 5).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.embedder import embed_texts
from app.vectorstore.chroma_client import get_docs_collection, get_sensor_collection, query


@dataclass
class RetrievedDocument:
    page_content: str
    metadata: dict


def retrieve_documents(
    query_text: str, k: int = 5, include_sensor_runs: bool = True, machine_id: str | None = None
) -> list[RetrievedDocument]:
    """Retrieve top-k chunks from knowledgebase_docs (and optionally sensor runs).

    machine_id (multi-machine support): restricts results to chunks tagged
    with this machine's id, so root-cause analysis for one machine never pulls
    in a service manual or historical run that belongs to a different machine.
    The dataset.csv seed chunks (migration 0003) predate multi-machine support
    and carry no machine_id tag — they intentionally stay untagged/global
    (still visible regardless of machine_id) since they're generic historical
    training data, not tied to any one physical machine.
    """
    embedding = embed_texts([query_text])[0]
    where = {"machine_id": machine_id} if machine_id else None

    results: list[RetrievedDocument] = []

    docs_collection = get_docs_collection()
    if docs_collection.count() > 0:
        res = query(docs_collection, embedding, n_results=k, where=where)
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        ids = res.get("ids", [[]])[0]
        for doc_text, meta, chroma_id in zip(docs, metas, ids):
            m = dict(meta or {})
            m["chroma_id"] = chroma_id
            results.append(RetrievedDocument(page_content=doc_text, metadata=m))

    if include_sensor_runs:
        sensor_collection = get_sensor_collection()
        if sensor_collection.count() > 0:
            res = query(sensor_collection, embedding, n_results=min(k, 3), where=where)
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            ids = res.get("ids", [[]])[0]
            for doc_text, meta, chroma_id in zip(docs, metas, ids):
                m = dict(meta or {})
                m["chroma_id"] = chroma_id
                results.append(RetrievedDocument(page_content=doc_text, metadata=m))

    return results
