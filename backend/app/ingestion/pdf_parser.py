"""Wrapper around MinerU for PDF -> Markdown parsing.

MinerU (https://github.com/opendatalab/MinerU) runs in its own container
(`mineru-service/`, mineru[pipeline]'s bundled `mineru-api` FastAPI server) —
NOT vendored into this backend image anymore. This backend only needs
`vendor/mineru_client.py` (a small httpx-only HTTP client, no `mineru`
package import of its own — see that module's docstring for why importing
`mineru.cli.api_client` directly still pulls in the whole model/OCR stack)
to talk to it; the actual `mineru[pipeline]` install, its OS-level deps
(libgl1/opencv), and its multi-hundred-MB model download all live in
mineru-service's image instead. This split exists so day-to-day backend code
changes stop invalidating the Docker layer cache for that model download.

Raises PdfParsingFailed if MinerU runs but produces no markdown output, or if
the underlying call to mineru-service fails for any reason (corrupt PDF,
service unreachable, task failure, etc.) — this endpoint must fail loudly,
not silently skip chunking.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

from app.config import settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "vendor"))
from mineru_client import MineruClientError, parse_via_remote_api  # noqa: E402  (path must be set up first)

logger = logging.getLogger(__name__)


class PdfParsingFailed(RuntimeError):
    """Raised when MinerU fails to parse a PDF (corrupt file, mineru-service error, etc.)."""


def parse_pdf_to_markdown(file_bytes: bytes, filename: str, language: str = "en") -> str:
    """Parse PDF bytes -> Markdown text via the mineru-service container.

    Mirrors the call pattern verified in code/knowledgebase.ipynb: MinerU's
    `pipeline` backend, `parse_method="auto"`, formula/table extraction on.

    This function is itself synchronous/blocking (parsing takes
    seconds-to-minutes) — callers from async routes must invoke it via
    `asyncio.to_thread(parse_pdf_to_markdown, ...)` to avoid blocking the
    event loop for the whole request. Because callers already do that, this
    function runs on a thread with no event loop of its own, so `asyncio.run()`
    below is safe (no "cannot be called from a running event loop" conflict).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        pdf_path = tmp_dir / filename
        pdf_path.write_bytes(file_bytes)
        output_dir = tmp_dir / "output"
        output_dir.mkdir(exist_ok=True)

        try:
            asyncio.run(
                parse_via_remote_api(
                    api_url=settings.MINERU_SERVICE_URL,
                    input_path=pdf_path,
                    output_dir=output_dir,
                    backend="pipeline",
                    parse_method="auto",
                    language=language,
                    formula_enable=True,
                    table_enable=True,
                )
            )
        except MineruClientError as exc:
            logger.exception("parse_pdf_to_markdown: mineru-service failed to parse %s", filename)
            raise PdfParsingFailed(f"MinerU gagal memparsing '{filename}': {exc}") from exc

        md_files = sorted(output_dir.rglob(f"{pdf_path.stem}*.md"))
        if not md_files:
            raise PdfParsingFailed(
                f"MinerU tidak menghasilkan file markdown untuk '{filename}' "
                "(kemungkinan file PDF kosong/corrupt atau tidak berisi konten "
                "yang bisa diekstrak)."
            )
        return md_files[0].read_text(encoding="utf-8")
