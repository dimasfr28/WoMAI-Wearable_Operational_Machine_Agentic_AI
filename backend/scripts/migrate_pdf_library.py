"""One-time migration: ingest every pre-existing PDF already sitting in the
host PDF library (/home/dimas/comfest/document, mounted at PDF_LIBRARY_DIR —
the "data" subfolder is intentionally skipped, it's dataset.csv already
handled by migration 0003) through the exact same pipeline as a manual
upload: MinerU parse -> chunk -> dedupe check -> embed -> Postgres +
Chroma `knowledgebase_docs`.

This is a script, not an Alembic migration: parsing 22 PDFs through MinerU's
OCR/layout models can take minutes-to-hours, and Alembic migrations are
expected to be fast/deterministic and run automatically on every container
start — blocking `alembic upgrade head` on that would stall every deploy.

Run manually: `docker compose exec backend python scripts/migrate_pdf_library.py`
Safe to re-run: skips any file whose name already has a Document row (matches
upload_pdf's replace-detection: keyed on original_filename).

NOTE (multi-machine support, migration 0008): this script predates per-machine
scoping and was already run once against the single implicit machine that now
exists as the backfilled "Haas Milling Machine 2023" row — it does not set
Document.machine_id or use pdf_library's now-per-machine save/path functions.
Left as-is since its one-time job is done; do not re-run against a
multi-machine dataset without updating it to accept a machine_id first.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Document, DocumentChunk  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.ingestion import pdf_library  # noqa: E402
from app.ingestion.duplicate_check import check_pdf_duplicate  # noqa: E402
from app.ingestion.embedder import embed_texts  # noqa: E402
from app.ingestion.pdf_parser import PdfParsingFailed, parse_pdf_to_markdown  # noqa: E402
from app.vectorstore.chroma_client import get_docs_collection, upsert_chunks  # noqa: E402


def _migrate_one(db, pdf_path: Path, existing_filenames: set[str]) -> None:
    filename = pdf_path.name
    if filename in existing_filenames:
        print(f"  [skip] {filename}: already in knowledgebase")
        return

    doc_name = pdf_path.stem
    file_bytes = pdf_path.read_bytes()

    document = Document(
        source_type="pdf",
        original_filename=filename,
        file_path=pdf_library.safe_filename(filename),
        doc_name=doc_name,
        status="processing",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        md_text = parse_pdf_to_markdown(file_bytes, filename)
    except PdfParsingFailed as exc:
        document.status = "failed"
        document.rejection_reason = str(exc)
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        print(f"  [fail] {filename}: MinerU parse failed: {exc}")
        return

    dup_result = check_pdf_duplicate(file_bytes, md_text, doc_name=doc_name, db=db)
    if dup_result.is_duplicate:
        document.status = "rejected_duplicate"
        document.rejection_reason = dup_result.reason
        document.file_sha256 = dup_result.file_hash
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        print(f"  [skip] {filename}: duplicate content ({dup_result.reason})")
        return

    candidate_chunks = dup_result.parsed_chunks
    if not candidate_chunks:
        document.status = "failed"
        document.rejection_reason = "no_chunks_extracted"
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        print(f"  [fail] {filename}: no chunks extracted")
        return

    document.file_sha256 = dup_result.file_hash

    db_chunks: list[DocumentChunk] = []
    for idx, chunk in enumerate(candidate_chunks):
        db_chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=idx,
            heading_1=chunk.get("heading_1"),
            heading_2=chunk.get("heading_2"),
            content=chunk["content"],
            chroma_id="",
        )
        db.add(db_chunk)
        db_chunks.append(db_chunk)
    db.flush()
    for db_chunk in db_chunks:
        db_chunk.chroma_id = str(db_chunk.id)
    db.commit()

    try:
        embeddings = embed_texts([c.content for c in db_chunks])
        collection = get_docs_collection()
        upsert_chunks(
            collection,
            ids=[c.chroma_id for c in db_chunks],
            embeddings=embeddings,
            documents=[c.content for c in db_chunks],
            metadatas=[
                {
                    "postgres_chunk_id": str(c.id),
                    "document_id": str(document.id),
                    "doc": document.doc_name,
                    "machine_type": document.machine_type or "Haas",
                    "heading_1": c.heading_1 or "",
                    "heading_2": c.heading_2 or "",
                    "chunk_index": c.chunk_index,
                }
                for c in db_chunks
            ],
        )
    except Exception as exc:  # noqa: BLE001
        document.status = "failed"
        document.rejection_reason = "chroma_upsert_failed"
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        print(f"  [fail] {filename}: Chroma upsert failed: {exc}")
        return

    document.status = "completed"
    document.processed_at = datetime.now(timezone.utc)
    db.commit()
    print(f"  [ok] {filename}: {len(db_chunks)} chunks ingested")


def main():
    library_root = pdf_library.library_dir()
    pdf_paths = sorted(
        p for p in library_root.rglob("*.pdf")
        if "data" not in p.relative_to(library_root).parts[:-1]
    )
    print(f"Found {len(pdf_paths)} PDF(s) under {library_root} (excluding data/)")

    db = SessionLocal()
    try:
        existing_filenames = {
            d.original_filename for d in db.query(Document).filter(Document.source_type == "pdf").all()
            if d.original_filename
        }
        for pdf_path in pdf_paths:
            try:
                _migrate_one(db, pdf_path, existing_filenames)
            except Exception as exc:  # noqa: BLE001 - one bad PDF must not abort the whole batch
                db.rollback()
                print(f"  [fail] {pdf_path.name}: unexpected error: {exc}")
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
