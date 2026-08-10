"""Wrapper around MinerU (vendored in-image) for PDF -> Markdown parsing.

MinerU (https://github.com/opendatalab/MinerU) is fully vendored into this
backend's Docker image (see Dockerfile: `mineru[pipeline]` in requirements.txt,
`vendor/mineru_demo.py`, build-time model pre-download, `MINERU_MODEL_SOURCE=
modelscope`), so parsing runs entirely inside this container — no external
MinerU service is required.

`mineru` does not expose a simple direct "parse this PDF" python function.
Its own documented usage pattern (github.com/opendatalab/MinerU/blob/master/
demo/demo.py, and how it was verified to work in
code/knowledgebase.ipynb) is to spin up a local `mineru-api` FastAPI subprocess
and drive it over HTTP: submit a parse task, poll for completion, download the
result zip, and extract it. `vendor/mineru_demo.py` is that exact demo module
vendored into this image; `run_demo()` is imported from it below and called
with the same parameters used in the notebook (`backend="pipeline"` — the
CPU-friendly OCR/layout backend this image installs; NOT "hybrid-engine"/
"vlm-engine", which need GPU-heavy extras this image deliberately does not
install).

MinerU is expected to always be importable/runnable in this image. If parsing
fails, `parse_pdf_to_markdown` lets the underlying exception propagate (wrapped
in `PdfParsingFailed` for anything unexpected) so callers
(routes_knowledgebase.py) can surface a clear 500 instead of silently producing
no chunks — there is intentionally no "unavailable, skip" fallback path
anymore, since MinerU is now a hard dependency baked into the image.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "vendor"))
from mineru_demo import run_demo  # noqa: E402  (path must be set up first)

logger = logging.getLogger(__name__)


class PdfParsingFailed(RuntimeError):
    """Raised when MinerU fails to parse a PDF (corrupt file, MinerU crash, etc.)."""


def _run_demo_in_new_loop(**kwargs) -> None:
    """Run the (async) MinerU run_demo() via asyncio.run() in a brand-new event
    loop. This must execute on its own thread: `parse_pdf_to_markdown` is called
    from an `async def` FastAPI route, so the calling thread already has a
    running event loop (uvicorn's) — asyncio.run() raises "cannot be called
    from a running event loop" if invoked directly there. A fresh thread has no
    event loop of its own, so asyncio.run() is safe here."""
    asyncio.run(run_demo(**kwargs))


def parse_pdf_to_markdown(file_bytes: bytes, filename: str, language: str = "en") -> str:
    """Parse PDF bytes -> Markdown text using the in-image MinerU installation.

    Mirrors the call pattern verified in code/knowledgebase.ipynb: MinerU's
    `pipeline` backend, `parse_method="auto"`, formula/table extraction on.

    This function is itself synchronous/blocking (MinerU parsing takes
    seconds-to-minutes) — callers from async routes must invoke it via
    `asyncio.to_thread(parse_pdf_to_markdown, ...)` to avoid blocking the
    event loop for the whole request.

    Raises PdfParsingFailed if MinerU runs but produces no markdown output, or
    if the underlying MinerU call raises for any reason (corrupt PDF, model
    loading error, subprocess crash, etc.) — this endpoint must fail loudly,
    not silently skip chunking.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        pdf_path = tmp_dir / filename
        pdf_path.write_bytes(file_bytes)
        output_dir = tmp_dir / "output"
        output_dir.mkdir(exist_ok=True)

        error: BaseException | None = None

        def _target() -> None:
            nonlocal error
            try:
                _run_demo_in_new_loop(
                    input_path=pdf_path,
                    output_dir=output_dir,
                    backend="pipeline",
                    parse_method="auto",
                    language=language,
                    formula_enable=True,
                    table_enable=True,
                )
            except BaseException as exc:  # noqa: BLE001 - captured, re-raised on the caller's thread below
                error = exc

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join()

        if error is not None:
            logger.exception("parse_pdf_to_markdown: MinerU failed to parse %s", filename, exc_info=error)
            raise PdfParsingFailed(f"MinerU gagal memparsing '{filename}': {error}") from error

        md_files = sorted(output_dir.rglob(f"{pdf_path.stem}*.md"))
        if not md_files:
            raise PdfParsingFailed(
                f"MinerU tidak menghasilkan file markdown untuk '{filename}' "
                "(kemungkinan file PDF kosong/corrupt atau tidak berisi konten "
                "yang bisa diekstrak)."
            )
        return md_files[0].read_text(encoding="utf-8")
