"""One-time seed script: populate documents/document_chunks (Postgres) + Chroma
`knowledgebase_docs` from the pre-parsed PDF markdown (code/output/**/auto/*.md,
bundled here as seed_data/pdf_markdown/*.md).

dataset.csv sensor-run chunks are NOT seeded here anymore — that now happens
automatically via Alembic migration 0003 (straight into Chroma
`knowledgebase_sensor_runs`, no Postgres documents/document_chunks rows), so the
only thing left to input manually into the running app is PDF files.

Run manually: `docker compose exec backend python scripts/seed_knowledgebase.py`
Safe to re-run: skips any doc_name that already exists in `documents`.
"""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Document, DocumentChunk  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.ingestion.chunking_docs import build_document_chunks  # noqa: E402
from app.ingestion.embedder import embed_texts  # noqa: E402
from app.vectorstore.chroma_client import get_docs_collection, upsert_chunks  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "seed_data"
PDF_MD_DIR = SEED_DIR / "pdf_markdown"
DATASET_CSV = SEED_DIR / "dataset.csv"


def _persist_chunks(db, chunks: list[dict], doc_name: str, source_type: str, collection):
    if not chunks:
        print(f"  [skip] {doc_name}: no chunks produced")
        return

    document = Document(source_type=source_type, doc_name=doc_name, machine_type="Haas", status="processing")
    if source_type == "pdf":
        document.original_filename = f"{doc_name}.pdf"
    db.add(document)
    db.commit()
    db.refresh(document)

    db_chunks = []
    for idx, chunk in enumerate(chunks):
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
    for c in db_chunks:
        c.chroma_id = str(c.id)
    db.commit()

    embeddings = embed_texts([c.content for c in db_chunks])
    upsert_chunks(
        collection,
        ids=[c.chroma_id for c in db_chunks],
        embeddings=embeddings,
        documents=[c.content for c in db_chunks],
        metadatas=[
            {
                "postgres_chunk_id": str(c.id),
                "document_id": str(document.id),
                "doc": doc_name,
                "machine_type": "Haas",
                "heading_1": c.heading_1 or "",
                "heading_2": c.heading_2 or "",
                "chunk_index": c.chunk_index,
            }
            for c in db_chunks
        ],
    )

    document.status = "completed"
    from datetime import datetime, timezone

    document.processed_at = datetime.now(timezone.utc)
    db.commit()
    print(f"  [ok] {doc_name}: {len(db_chunks)} chunks seeded")


def main():
    db = SessionLocal()
    try:
        existing_doc_names = {d.doc_name for d in db.query(Document).all()}

        docs_collection = get_docs_collection()

        print("Seeding PDF documents...")
        for md_path in sorted(PDF_MD_DIR.glob("*.md")):
            doc_name = md_path.stem
            if doc_name in existing_doc_names:
                print(f"  [skip] {doc_name}: already exists")
                continue
            md_text = md_path.read_text(encoding="utf-8")
            chunks = build_document_chunks(md_text, doc_name=doc_name, machine_type="Haas")
            _persist_chunks(db, chunks, doc_name=doc_name, source_type="pdf", collection=docs_collection)

        print("Seeding raw sensor_readings from dataset.csv (for KNN/SHAP background data)...")
        _seed_sensor_readings(db)

        print("Done.")
    finally:
        db.close()


def _seed_sensor_readings(db):
    from app.db.models import SensorReading, SensorRun
    from datetime import datetime, timedelta, timezone

    if db.query(SensorReading).count() > 0:
        print("  [skip] sensor_readings already populated")
        return
    if not DATASET_CSV.exists():
        print(f"  [warn] {DATASET_CSV} not found, skipping sensor_readings seed")
        return

    with DATASET_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    from app.ingestion.chunking_sensor import segment_runs_by_tool_wear

    run_bounds = segment_runs_by_tool_wear(rows)
    base_time = datetime.now(timezone.utc) - timedelta(days=365)
    t = base_time
    for run_idx, (start, end) in enumerate(run_bounds):
        run_rows = rows[start:end]
        failure_count = sum(int(r["Machine failure"]) for r in run_rows)
        run = SensorRun(
            run_label=f"Run {run_idx + 1}",
            start_timestamp=t,
            end_timestamp=t,
            sample_count=len(run_rows),
            failure_count=failure_count,
            is_closed=True,
        )
        db.add(run)
        db.flush()
        for r in run_rows:
            t += timedelta(seconds=30)
            db.add(
                SensorReading(
                    run_id=run.id,
                    reading_timestamp=t,
                    air_temperature_k=float(r["Air temperature K"]),
                    process_temperature_k=float(r["Process temperature K"]),
                    rotational_speed_rpm=int(float(r["Rotational speed rpm"])),
                    tool_wear_min=float(r["Tool wear min"]),
                    machine_failure=bool(int(r["Machine failure"])),
                    input_source="manual_form",
                )
            )
        run.end_timestamp = t
        t += timedelta(minutes=5)
    db.commit()
    print(f"  [ok] seeded {len(rows)} sensor_readings across {len(run_bounds)} runs")


if __name__ == "__main__":
    main()
