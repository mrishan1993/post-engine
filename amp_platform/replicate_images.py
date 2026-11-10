"""Live image generation via Replicate (Flux)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from amp_platform.live_http import download_to, new_job_path
from config.settings import get_settings

# Official Flux Schnell on Replicate
REPLICATE_MODEL = "black-forest-labs/flux-schnell"


class ReplicateImageError(RuntimeError):
    pass


def replicate_configured() -> bool:
    return bool(get_settings().replicate_api_token)


def generate_image(
    prompt: str,
    *,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
    out_path: Path | None = None,
) -> Path:
    settings = get_settings()
    token = settings.replicate_api_token
    if not token:
        raise ReplicateImageError("REPLICATE_API_TOKEN not configured")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }
    payload: dict[str, Any] = {
        "input": {
            "prompt": prompt,
            "num_outputs": 1,
            "aspect_ratio": "9:16" if height >= width else "16:9",
            "output_format": "png",
        }
    }
    if seed is not None:
        payload["input"]["seed"] = int(seed)

    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        resp = client.post(
            f"https://api.replicate.com/v1/models/{REPLICATE_MODEL}/predictions",
            headers=headers,
            json=payload,
        )
        if resp.status_code >= 400:
            raise ReplicateImageError(f"replicate submit failed: {resp.status_code} {resp.text[:500]}")
        body = resp.json()

        # Prefer wait may return completed; otherwise poll
        status = body.get("status")
        get_url = body.get("urls", {}).get("get") or f"https://api.replicate.com/v1/predictions/{body.get('id')}"
        for _ in range(90):
            if status == "succeeded":
                break
            if status in {"failed", "canceled"}:
                raise ReplicateImageError(f"replicate failed: {body}")
            time.sleep(2)
            poll = client.get(get_url, headers={"Authorization": f"Bearer {token}"})
            poll.raise_for_status()
            body = poll.json()
            status = body.get("status")
        if status != "succeeded":
            raise ReplicateImageError(f"replicate timed out: {body}")

    output = body.get("output")
    if isinstance(output, list):
        url = output[0] if output else None
    else:
        url = output
    if not url:
        raise ReplicateImageError(f"replicate no output: {body}")

    path = out_path or new_job_path("replicate", "png")
    download_to(path, str(url))
    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "provider": "replicate",
                "model": REPLICATE_MODEL,
                "prompt": prompt[:500],
                "width": width,
                "height": height,
                "seed": seed,
                "prediction_id": body.get("id"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
