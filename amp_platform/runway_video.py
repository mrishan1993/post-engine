"""Live video generation via Runway API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from amp_platform.live_http import download_to, new_job_path
from config.settings import get_settings

RUNWAY_BASE = "https://api.dev.runwayml.com/v1"
RUNWAY_VERSION = "2024-11-06"


class RunwayError(RuntimeError):
    pass


def runway_configured() -> bool:
    return bool(get_settings().runway_api_key)


def _headers() -> dict[str, str]:
    key = get_settings().runway_api_key or ""
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Runway-Version": RUNWAY_VERSION,
    }


def generate_video(
    prompt: str,
    *,
    duration_sec: float = 5.0,
    ratio: str = "720:1280",
    seed: int | None = None,
    image_url: str | None = None,
    out_path: Path | None = None,
) -> Path:
    if not runway_configured():
        raise RunwayError("RUNWAY_API_KEY not configured")

    # Runway text_to_video / image_to_video
    dur = int(max(2, min(10, round(duration_sec))))
    if image_url:
        endpoint = f"{RUNWAY_BASE}/image_to_video"
        payload: dict[str, Any] = {
            "model": "gen4_turbo",
            "promptText": prompt[:1000],
            "promptImage": image_url,
            "ratio": ratio,
            "duration": dur,
        }
    else:
        endpoint = f"{RUNWAY_BASE}/text_to_video"
        payload = {
            "model": "gen4_turbo",
            "promptText": prompt[:1000],
            "ratio": ratio,
            "duration": dur,
        }
    if seed is not None:
        payload["seed"] = int(seed) % 2147483647

    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        submit = client.post(endpoint, headers=_headers(), json=payload)
        if submit.status_code >= 400:
            raise RunwayError(f"runway submit failed: {submit.status_code} {submit.text[:600]}")
        body = submit.json()
        task_id = body.get("id")
        if not task_id:
            raise RunwayError(f"runway missing task id: {body}")

        result = None
        for _ in range(120):
            st = client.get(f"{RUNWAY_BASE}/tasks/{task_id}", headers=_headers())
            st.raise_for_status()
            data = st.json()
            status = (data.get("status") or "").upper()
            if status in {"SUCCEEDED", "COMPLETED"}:
                result = data
                break
            if status in {"FAILED", "CANCELLED"}:
                raise RunwayError(f"runway task failed: {data}")
            time.sleep(3)
        if result is None:
            raise RunwayError("runway task timed out")

    output = result.get("output") or []
    url = output[0] if isinstance(output, list) and output else None
    if not url:
        raise RunwayError(f"runway no output: {result}")

    path = out_path or new_job_path("runway", "mp4")
    download_to(path, str(url))
    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "provider": "runway",
                "task_id": task_id,
                "prompt": prompt[:500],
                "duration_sec": dur,
                "ratio": ratio,
                "seed": seed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
