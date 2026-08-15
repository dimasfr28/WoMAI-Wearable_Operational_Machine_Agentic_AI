"""Thin HTTP client for a remote mineru-api server (mineru[pipeline]'s bundled
FastAPI service, run as its own long-lived process in the `mineru-service`
container — see mineru-service/Dockerfile.dev).

Replaces the previous approach of importing `mineru.cli.api_client` /
`mineru.cli.common` from the `mineru` package directly: those modules
transitively import most of MinerU's own model/OCR stack (torch, opencv,
onnxruntime, transformers) at import time even when only used as an HTTP
client — importing them alone defeats the point of running MinerU in its own
container, since the backend image would still need `mineru[pipeline]`
installed just to send a request. This module implements only the subset of
MinerU's client protocol actually used here (submit -> poll -> download ->
extract), talking to an always-external `api_url` — the "spawn a local
mineru-api subprocess" mode (MinerU's own `LocalAPIServer`) is intentionally
not reimplemented, since this backend never runs MinerU in-process anymore.

Protocol constants/shapes below are read directly from mineru==3.4.4's
`mineru.cli.api_client`/`mineru.cli.api_protocol` source (the version pinned
in mineru-service/requirements.txt) — keep both in sync if that version bumps.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import tempfile
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

import httpx

API_PROTOCOL_VERSION = 2
HEALTH_ENDPOINT = "/health"
TASKS_ENDPOINT = "/tasks"
TASK_STATUS_POLL_INTERVAL_SECONDS = 1.0
TASK_RESULT_TIMEOUT_SECONDS = 3600.0
TASK_RESULT_DOWNLOAD_TIMEOUT_SECONDS = 600.0
DEFAULT_EFFORT = "medium"


class MineruClientError(RuntimeError):
    """Raised for any mineru-api protocol/HTTP failure (bad health, submit
    rejected, task failed, bad zip, etc.) — callers treat this the same as any
    other unexpected parsing failure."""


def _http_timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=10, read=60, write=300, pool=30)


def _response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        text = response.text.strip()
        return text or response.reason_phrase
    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
    return json.dumps(payload, ensure_ascii=False)


@dataclass(frozen=True)
class _SubmitResponse:
    task_id: str
    status_url: str
    result_url: str


async def _check_health(client: httpx.AsyncClient, base_url: str) -> None:
    response = await client.get(f"{base_url}{HEALTH_ENDPOINT}")
    if response.status_code != 200:
        raise MineruClientError(
            f"Failed to query mineru-api health at {base_url}: "
            f"{response.status_code} {_response_detail(response)}"
        )
    payload = response.json()
    if payload.get("status") != "healthy":
        raise MineruClientError(f"mineru-api at {base_url} is not healthy: {payload}")
    if payload.get("protocol_version") != API_PROTOCOL_VERSION:
        raise MineruClientError(
            f"mineru-api at {base_url} speaks protocol_version={payload.get('protocol_version')}, "
            f"this client expects {API_PROTOCOL_VERSION}"
        )


def _submit_parse_task_sync(base_url: str, file_path: Path, upload_name: str, form_data: dict) -> _SubmitResponse:
    task_url = f"{base_url}{TASKS_ENDPOINT}"
    mime_type = mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
    with httpx.Client(timeout=_http_timeout(), follow_redirects=True) as sync_client:
        with ExitStack() as stack:
            file_handle = stack.enter_context(open(file_path, "rb"))
            response = sync_client.post(
                task_url,
                data=form_data,
                files=[("files", (upload_name, file_handle, mime_type))],
            )

    if response.status_code != 202:
        raise MineruClientError(
            f"Failed to submit parsing task to {task_url}: "
            f"{response.status_code} {_response_detail(response)}"
        )
    payload = response.json()
    task_id, status_url, result_url = payload.get("task_id"), payload.get("status_url"), payload.get("result_url")
    if not isinstance(task_id, str) or not isinstance(status_url, str) or not isinstance(result_url, str):
        raise MineruClientError(f"mineru-api returned an invalid task payload: {payload}")
    return _SubmitResponse(task_id=task_id, status_url=status_url, result_url=result_url)


async def _wait_for_task_result(client: httpx.AsyncClient, submit_response: _SubmitResponse) -> None:
    deadline = asyncio.get_running_loop().time() + TASK_RESULT_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        try:
            response = await client.get(submit_response.status_url)
        except httpx.ReadTimeout:
            await asyncio.sleep(TASK_STATUS_POLL_INTERVAL_SECONDS)
            continue
        if response.status_code != 200:
            raise MineruClientError(
                f"Failed to query task status: {response.status_code} {_response_detail(response)}"
            )
        payload = response.json()
        status = payload.get("status")
        if status in {"pending", "processing"}:
            await asyncio.sleep(TASK_STATUS_POLL_INTERVAL_SECONDS)
            continue
        if status == "completed":
            return
        raise MineruClientError(f"mineru-api task {submit_response.task_id} failed: {payload}")
    raise MineruClientError(f"Timed out waiting for mineru-api task {submit_response.task_id}")


async def _download_result_zip(client: httpx.AsyncClient, submit_response: _SubmitResponse) -> Path:
    zip_fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="mineru_client_result_")
    os.close(zip_fd)
    zip_file_path = Path(zip_path)
    download_timeout = httpx.Timeout(
        connect=10, read=TASK_RESULT_DOWNLOAD_TIMEOUT_SECONDS, write=300, pool=30
    )
    try:
        async with client.stream("GET", submit_response.result_url, timeout=download_timeout) as response:
            if response.status_code != 200:
                await response.aread()
                raise MineruClientError(
                    f"Failed to download result ZIP for task {submit_response.task_id}: "
                    f"{response.status_code} {_response_detail(response)}"
                )
            content_type = response.headers.get("content-type", "")
            if "application/zip" not in content_type:
                raise MineruClientError(
                    f"Expected a ZIP result, got content-type={content_type or 'unknown'}"
                )
            with open(zip_file_path, "wb") as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
    except Exception:
        zip_file_path.unlink(missing_ok=True)
        raise
    return zip_file_path


def _safe_extract_zip(zip_path: Path, output_dir: Path) -> None:
    """Path-traversal-safe zip extraction — identical logic to MinerU's own
    `safe_extract_zip`, reimplemented here to avoid importing the package."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_root = output_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as zip_file:
        for member in zip_file.infolist():
            member_path = PurePosixPath(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise MineruClientError(f"Refusing to extract unsafe ZIP entry: {member.filename}")
            target_path = (output_root / Path(*member_path.parts)).resolve()
            if target_path != output_root and output_root not in target_path.parents:
                raise MineruClientError(f"Refusing to extract unsafe ZIP entry: {member.filename}")
            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(member, "r") as source, open(target_path, "wb") as handle:
                handle.write(source.read())


async def parse_via_remote_api(
    *,
    api_url: str,
    input_path: Path,
    output_dir: Path,
    backend: str = "pipeline",
    parse_method: str = "auto",
    language: str = "en",
    formula_enable: bool = True,
    table_enable: bool = True,
) -> None:
    """Submit `input_path` to the remote mineru-api at `api_url`, poll until
    done, download and extract the result into `output_dir` — health check,
    submit, poll, download, extract."""
    base_url = api_url.rstrip("/")
    form_data = {
        "lang_list": [language],
        "backend": backend,
        "effort": DEFAULT_EFFORT,
        "parse_method": parse_method,
        "formula_enable": str(formula_enable).lower(),
        "table_enable": str(table_enable).lower(),
        "image_analysis": "true",
        "return_md": "true",
        "return_middle_json": "false",
        "return_model_output": "false",
        "return_content_list": "false",
        "return_images": "false",
        "response_format_zip": "true",
        "return_original_file": "false",
        "client_side_output_generation": "false",
        "start_page_id": "0",
        "end_page_id": "99999",
    }

    async with httpx.AsyncClient(timeout=_http_timeout(), follow_redirects=True) as client:
        await _check_health(client, base_url)
        submit_response = await asyncio.to_thread(
            _submit_parse_task_sync, base_url, input_path, input_path.name, form_data
        )
        await _wait_for_task_result(client, submit_response)
        zip_path = await _download_result_zip(client, submit_response)

    try:
        _safe_extract_zip(zip_path, output_dir)
    finally:
        zip_path.unlink(missing_ok=True)
