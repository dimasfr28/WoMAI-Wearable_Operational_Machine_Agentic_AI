"""Section 7: GET /knowledgebase/documents, POST /knowledgebase/upload/pdf."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.models import Document, DocumentChunk, Machine, User
from app.db.session import get_db
from app.ingestion import pdf_library
from app.ingestion.duplicate_check import check_pdf_duplicate
from app.ingestion.embedder import embed_texts
from app.ingestion.pdf_parser import PdfParsingFailed, parse_pdf_to_markdown
from app.schemas.knowledgebase import ChunkOut, DocumentOut, FilenameCheckOut, UploadPdfResponseOut
from app.vectorstore.chroma_client import delete_chunks, get_docs_collection, upsert_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledgebase", tags=["knowledgebase"])


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(machine_id: str, db: Session = Depends(get_db)):
    # source_type="sensor_numeric" docs are auto-generated per closed sensor run
    # purely so CRAG can retrieve similar historical runs (see
    # routes_sensor.py::_close_run_and_build_chunk) — they aren't user-uploaded
    # knowledge and shouldn't clutter the Knowledgebase document library.
    docs = (
        db.query(Document)
        .filter(Document.machine_id == machine_id, Document.source_type != "sensor_numeric")
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    out = []
    for d in docs:
        chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == d.id).count()
        out.append(
            DocumentOut(
                id=str(d.id),
                source_type=d.source_type,
                original_filename=d.original_filename,
                doc_name=d.doc_name,
                machine_type=d.machine_type,
                status=d.status,
                rejection_reason=d.rejection_reason,
                uploaded_at=d.uploaded_at,
                processed_at=d.processed_at,
                chunk_count=chunk_count,
            )
        )
    return out


@router.get("/upload/check-filename", response_model=FilenameCheckOut)
def check_filename(filename: str, machine_id: str, user: User = Depends(get_current_user)):
    """Called by the frontend before an actual upload so it can show a
    replace-or-cancel confirmation modal when a same-named file already sits
    in this machine's library — separate from the content-based duplicate
    check in check_pdf_duplicate, which only runs after parsing."""
    return FilenameCheckOut(exists=pdf_library.exists(machine_id, filename))


@router.post("/upload/pdf", response_model=UploadPdfResponseOut)
async def upload_pdf(
    machine_id: str,
    file: UploadFile = File(...),
    replace: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File harus berformat .pdf")

    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")

    file_bytes = await file.read()
    doc_name = file.filename.rsplit(".", 1)[0]

    if pdf_library.exists(machine_id, file.filename):
        if not replace:
            raise HTTPException(
                status_code=409,
                detail={"error": "filename_exists", "filename": file.filename},
            )
        existing = (
            db.query(Document)
            .filter(Document.original_filename == file.filename, Document.machine_id == machine_id)
            .first()
        )
        if existing is not None:
            _delete_document_fully(db, existing)

    pdf_library.save(machine_id, file.filename, file_bytes)

    document = Document(
        machine_id=machine_id,
        source_type="pdf",
        original_filename=file.filename,
        file_path=pdf_library.relative_path(machine_id, file.filename),
        doc_name=doc_name,
        status="processing",
        uploaded_by=user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        # parse_pdf_to_markdown is a blocking call (MinerU parsing takes
        # seconds-to-minutes) — run it off the event loop so this request
        # doesn't stall every other concurrent request being served by uvicorn.
        md_text = await asyncio.to_thread(parse_pdf_to_markdown, file_bytes, file.filename)
    except PdfParsingFailed as exc:
        document.status = "failed"
        document.rejection_reason = str(exc)
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    dup_result = check_pdf_duplicate(file_bytes, md_text, doc_name=doc_name, db=db, machine_id=machine_id)

    if dup_result.is_duplicate:
        document.status = "rejected_duplicate"
        document.rejection_reason = dup_result.reason
        document.file_sha256 = dup_result.file_hash
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={"error": "duplicate_content", "reason": dup_result.reason, "ratio": dup_result.ratio},
        )

    candidate_chunks = dup_result.parsed_chunks
    if not candidate_chunks:
        document.status = "failed"
        document.rejection_reason = "no_chunks_extracted"
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=422, detail="Tidak ada konten yang bisa di-chunk dari dokumen ini")

    document.file_sha256 = dup_result.file_hash

    # Postgres commit dulu, baru Chroma upsert (Section 6.2); kalau Chroma gagal,
    # rollback status jadi 'failed' supaya bisa retry manual.
    db_chunks: list[DocumentChunk] = []
    try:
        for idx, chunk in enumerate(candidate_chunks):
            db_chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=idx,
                heading_1=chunk.get("heading_1"),
                heading_2=chunk.get("heading_2"),
                content=chunk["content"],
                chroma_id="",  # filled below once we know the row id
            )
            db.add(db_chunk)
            db_chunks.append(db_chunk)
        db.flush()  # assign ids without committing yet
        for db_chunk in db_chunks:
            db_chunk.chroma_id = str(db_chunk.id)
        db.commit()
    except Exception:
        db.rollback()
        document.status = "failed"
        document.rejection_reason = "postgres_commit_failed"
        db.commit()
        logger.exception("upload_pdf: failed to commit chunks to Postgres")
        raise HTTPException(status_code=500, detail="Gagal menyimpan chunk ke database") from None

    try:
        # embed_texts is now a blocking HTTP call to embedding-service (see
        # app/ingestion/embedder.py) — this route is async def, so it must be
        # offloaded to a thread to avoid stalling uvicorn's event loop for
        # every other concurrent request while waiting on the network call.
        embeddings = await asyncio.to_thread(embed_texts, [c.content for c in db_chunks])
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
                    "machine_id": str(document.machine_id) if document.machine_id else "",
                    "doc": document.doc_name,
                    "machine_type": document.machine_type or "Haas",
                    "heading_1": c.heading_1 or "",
                    "heading_2": c.heading_2 or "",
                    "chunk_index": c.chunk_index,
                }
                for c in db_chunks
            ],
        )
    except Exception:
        document.status = "failed"
        document.rejection_reason = "chroma_upsert_failed"
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        logger.exception("upload_pdf: failed to upsert embeddings to Chroma")
        raise HTTPException(status_code=500, detail="Gagal menyimpan embedding ke Chroma (retry manual diperlukan)") from None

    document.status = "completed"
    document.processed_at = datetime.now(timezone.utc)
    db.commit()

    return UploadPdfResponseOut(
        status="completed",
        document_id=str(document.id),
        chunks=[
            ChunkOut(heading_1=c.heading_1, heading_2=c.heading_2, content=c.content, chunk_index=c.chunk_index)
            for c in db_chunks
        ],
    )


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
def get_document_chunks(document_id: str, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    return [
        ChunkOut(heading_1=c.heading_1, heading_2=c.heading_2, content=c.content, chunk_index=c.chunk_index)
        for c in chunks
    ]


def _delete_document_fully(db: Session, document: Document) -> None:
    """Delete a document and all its chunks — Postgres (cascade, see
    Document.chunks relationship), the matching Chroma vectors (Chroma has no
    FK cascade of its own, so this must be done explicitly), and the physical
    PDF file on disk (if any — sensor-derived documents have none)."""
    chroma_ids = [
        chunk_id
        for (chunk_id,) in db.query(DocumentChunk.chroma_id).filter(DocumentChunk.document_id == document.id).all()
        if chunk_id
    ]
    try:
        delete_chunks(get_docs_collection(), chroma_ids)
    except Exception:
        # Don't block the delete on a Chroma hiccup — orphaned vectors are
        # harmless (never surfaced without a matching Postgres chunk row) and
        # can be swept later; the user's intent ("remove this document") must
        # still succeed on the Postgres side below.
        logger.exception("_delete_document_fully: failed to delete %d Chroma vectors for document %s", len(chroma_ids), document.id)

    if document.file_path:
        pdf_library.delete(document.file_path)

    db.delete(document)  # cascades to document_chunks (see models.py)
    db.commit()


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    _delete_document_fully(db, document)
    return None
