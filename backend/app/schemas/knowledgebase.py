from datetime import datetime

from pydantic import BaseModel


class ChunkOut(BaseModel):
    heading_1: str | None
    heading_2: str | None
    content: str
    chunk_index: int


class DocumentOut(BaseModel):
    id: str
    source_type: str
    original_filename: str | None
    doc_name: str
    machine_type: str | None
    status: str
    rejection_reason: str | None
    uploaded_at: datetime
    processed_at: datetime | None
    chunk_count: int = 0

    model_config = {"from_attributes": True}


class UploadPdfResponseOut(BaseModel):
    status: str
    document_id: str | None = None
    chunks: list[ChunkOut] | None = None


class FilenameCheckOut(BaseModel):
    exists: bool


class DuplicateErrorOut(BaseModel):
    error: str = "duplicate_content"
    reason: str
    ratio: float | None = None
