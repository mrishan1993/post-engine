"""Shared helpers for live generation HTTP providers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from config.settings import get_settings


def storage_generated(subdir: str) -> Path:
    root = Path(get_settings().storage_root) / "generated" / subdir
    root.mkdir(parents=True, exist_ok=True)
    return root


def download_to(path: Path, url: str, *, timeout: float = 120.0, headers: dict[str, str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers=headers or {})
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return path


def write_b64_image(path: Path, b64_data: str) -> Path:
    import base64

    raw = b64_data
    if "," in raw and raw.strip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(raw))
    return path


def new_job_path(subdir: str, ext: str) -> Path:
    return storage_generated(subdir) / f"{uuid4().hex[:16]}.{ext.lstrip('.')}"


def poll_until(
    *,
    check,
    timeout_sec: float = 300.0,
    interval_sec: float = 2.5,
) -> Any:
    deadline = time.time() + timeout_sec
    last = None
    while time.time() < deadline:
        last = check()
        if last is not None:
            return last
        time.sleep(interval_sec)
    raise TimeoutError(f"provider poll timed out after {timeout_sec}s; last={last!r}")
