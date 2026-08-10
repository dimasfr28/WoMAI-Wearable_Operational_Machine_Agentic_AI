"""seed dataset.csv sensor-run chunks directly into Chroma — the only thing a user
should have to input manually into the running app is PDF files, so the historical
dataset.csv chunking (previously a manual `scripts/seed_knowledgebase.py` step) now
runs automatically at migration time. Chunks are pushed straight to the Chroma
`knowledgebase_sensor_runs` collection; no `documents`/`document_chunks` Postgres rows
are created for them (per explicit scope: chunked sensor runs only, not shown in the
Knowledgebase UI, and not raw sensor_readings/sensor_runs — those stay unseeded).

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-05

"""
import csv
from pathlib import Path
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DATASET_CSV = Path(__file__).resolve().parents[4] / "seed_data" / "dataset.csv"
DOC_NAME = "dataset"


def upgrade() -> None:
    from app.ingestion.chunking_sensor import build_chunks_from_dataset_rows
    from app.ingestion.embedder import embed_texts
    from app.vectorstore.chroma_client import get_sensor_collection, upsert_chunks

    if not DATASET_CSV.exists():
        print(f"  [warn] {DATASET_CSV} not found, skipping dataset sensor-run seed")
        return

    sensor_collection = get_sensor_collection()

    existing = sensor_collection.get(where={"doc": DOC_NAME}, limit=1)
    if existing["ids"]:
        print("  [skip] dataset sensor-run chunks already seeded in Chroma")
        return

    with DATASET_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    chunks = build_chunks_from_dataset_rows(rows, doc_name=DOC_NAME)
    if not chunks:
        print("  [skip] dataset: no chunks produced")
        return

    ids = [f"dataset-run-{idx}" for idx in range(len(chunks))]
    embeddings = embed_texts([c["content"] for c in chunks])
    upsert_chunks(
        sensor_collection,
        ids=ids,
        embeddings=embeddings,
        documents=[c["content"] for c in chunks],
        metadatas=[
            {
                "doc": c["doc"],
                "machine_type": c["machine_type"],
                "heading_1": c.get("heading_1") or "",
                "heading_2": c.get("heading_2") or "",
                "chunk_index": idx,
            }
            for idx, c in enumerate(chunks)
        ],
    )
    print(f"  [ok] dataset: {len(chunks)} sensor-run chunks seeded to Chroma")


def downgrade() -> None:
    from app.vectorstore.chroma_client import get_sensor_collection, delete_chunks

    sensor_collection = get_sensor_collection()
    existing = sensor_collection.get(where={"doc": DOC_NAME})
    delete_chunks(sensor_collection, existing["ids"])
