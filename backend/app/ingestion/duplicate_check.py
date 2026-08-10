"""Upload PDF — cek duplikat — Section 6.1."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Document
from app.ingestion.chunking_docs import build_document_chunks
from app.ingestion.embedder import embed_texts
from app.vectorstore.chroma_client import get_docs_collection, query_top1


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    reason: str | None = None
    ratio: float | None = None
    file_hash: str = ""
    parsed_chunks: list[dict] = field(default_factory=list)


def sha256_bytes(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def check_pdf_duplicate(
    file_bytes: bytes, md_text: str, doc_name: str, db: Session, machine_id: str | None = None
) -> DuplicateCheckResult:
    """Section 6.1: lapis 1 exact-file hash, lapis 2 semantic similarity per-chunk.

    `md_text` is the already-parsed markdown (from pdf_parser.parse_pdf_to_markdown),
    passed in so parsing only ever happens once per upload.

    machine_id (multi-machine support): both duplicate layers are scoped to this
    machine — the same manual PDF can legitimately be uploaded once per machine
    (e.g. two identical Haas VF-2 units each get their own copy), so a match
    against a DIFFERENT machine's document must not block the upload.
    """
    file_hash = sha256_bytes(file_bytes)

    # Lapis 1: exact-file hash (scoped to this machine)
    exists_query = db.query(Document).filter(Document.file_sha256 == file_hash)
    if machine_id:
        exists_query = exists_query.filter(Document.machine_id == machine_id)
    exists = exists_query.first()
    if exists is not None:
        return DuplicateCheckResult(is_duplicate=True, reason="exact_file_match", file_hash=file_hash)

    # Lapis 2: semantic similarity — parsing sudah dilakukan oleh caller (md_text),
    # di sini kita hanya chunk (TANPA disimpan) dan cek tiap chunk baru terhadap Chroma.
    candidate_chunks = build_document_chunks(md_text, doc_name=doc_name)

    if not candidate_chunks:
        return DuplicateCheckResult(is_duplicate=False, file_hash=file_hash, parsed_chunks=candidate_chunks)

    collection = get_docs_collection()
    # Kalau koleksi masih kosong, tidak ada apapun untuk dibandingkan -> otomatis bukan duplikat.
    if collection.count() == 0:
        return DuplicateCheckResult(is_duplicate=False, file_hash=file_hash, parsed_chunks=candidate_chunks)

    embeddings = embed_texts([c["content"] for c in candidate_chunks])
    where = {"machine_id": machine_id} if machine_id else None

    duplicate_hits = 0
    for emb in embeddings:
        result = query_top1(collection, emb, where=where)
        distances = result.get("distances") or [[]]
        if not distances or not distances[0]:
            continue
        top_similarity = 1 - distances[0][0]  # asumsi cosine distance
        if top_similarity >= settings.DUPLICATE_CHUNK_SIMILARITY_THRESHOLD:
            duplicate_hits += 1

    duplicate_ratio = duplicate_hits / len(candidate_chunks)
    if duplicate_ratio >= settings.DUPLICATE_CHUNK_RATIO_THRESHOLD:
        return DuplicateCheckResult(
            is_duplicate=True,
            reason="semantic_duplicate",
            ratio=duplicate_ratio,
            file_hash=file_hash,
        )

    return DuplicateCheckResult(is_duplicate=False, file_hash=file_hash, parsed_chunks=candidate_chunks)
