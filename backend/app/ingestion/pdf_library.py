"""Physical PDF library on disk (/data/pdf_library, host-mounted from
/home/dimas/comfest/document) — Section 7 upload now persists the original
file here instead of parsing-then-discarding it, so uploads survive restarts
and the pre-existing manuals under that same host directory can be migrated
in place by the same code path.

Multi-machine support: files live under a per-machine subfolder
(<machine_id>/<filename>) so two machines can each have a PDF with the same
name without colliding. Pre-existing files from before multi-machine support
sit flat at the library root (no subfolder) — those all belong to the
backfilled default machine (see migration 0008) and are looked up via
`legacy=True` by callers that know a Document predates this change (i.e. has
no machine-scoped subfolder in its stored file_path)."""
from __future__ import annotations

import re
from pathlib import Path

from app.config import settings


def library_dir() -> Path:
    path = Path(settings.PDF_LIBRARY_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


_UNSAFE_CHARS_RE = re.compile(r"[\/\\\x00]")


def safe_filename(filename: str) -> str:
    """Strip path separators/null bytes from a user-supplied filename — it is
    joined onto library_dir() below, so nothing here may escape that directory."""
    name = _UNSAFE_CHARS_RE.sub("_", filename).strip()
    return name or "unnamed.pdf"


def machine_dir(machine_id: str) -> Path:
    path = library_dir() / str(machine_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_path(machine_id: str, filename: str) -> Path:
    return machine_dir(machine_id) / safe_filename(filename)


def relative_path(machine_id: str, filename: str) -> str:
    """Value stored in Document.file_path — relative to library_dir(), used by
    delete() to find the file again without needing machine_id passed back in."""
    return f"{machine_id}/{safe_filename(filename)}"


def exists(machine_id: str, filename: str) -> bool:
    return library_path(machine_id, filename).is_file()


def save(machine_id: str, filename: str, file_bytes: bytes) -> Path:
    path = library_path(machine_id, filename)
    path.write_bytes(file_bytes)
    return path


def delete(relative_file_path: str) -> None:
    """`relative_file_path` is whatever was stored in Document.file_path —
    either "<machine_id>/<filename>" for new uploads, or a bare filename for
    pre-multi-machine rows (still valid: they sit flat at the library root)."""
    path = library_dir() / relative_file_path
    path.unlink(missing_ok=True)
