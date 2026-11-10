"""Live image generation via fal.ai Flux."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from amp_platform.live_http import download_to, new_job_path
from config.settings import get_settings


FAL_FLUX_MODEL = "fal-ai/flux/schnell"


class FalImageError(RuntimeError):
    pass


def fal_configured() -> bool:
    return bool(get_settings().fal_key)


def generate_image(
    prompt: str,
    *,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
    out_path: Path | None = None,
) -> Path:
    settings = get_settings()
    key = settings.fal_key
    if not key:
        raise FalImageError("FAL_KEY not configured")

    headers = {
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "prompt": prompt,
        "image_size": {"width": int(width), "height": int(height)},
        "num_images": 1,
        "enable_safety_checker": True,
    }
    if seed is not None:
        payload["seed"] = int(seed)

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        submit = client.post(
            f"https://queue.fal.run/{FAL_FLUX_MODEL}",
            headers=headers,
            json=payload,
        )
        if submit.status_code >= 400:
            raise FalImageError(f"fal submit failed: {submit.status_code} {submit.text[:500]}")
        body = submit.json()
        status_url = body.get("status_url")
        response_url = body.get("response_url")
        request_id = body.get("request_id") or uuid4().hex

        # Some responses complete inline
        if body.get("images"):
            result = body
        else:
            if not status_url:
                raise FalImageError(f"fal missing status_url: {body}")
            result = None
            for _ in range(120):
                st = client.get(status_url, headers=headers)
                st.raise_for_status()
                data = st.json()
                status = (data.get("status") or "").upper()
                if status in {"COMPLETED", "OK", "SUCCESS"}:
                    if response_url:
                        rr = client.get(response_url, headers=headers)
                        rr.raise_for_status()
                        result = rr.json()
                    else:
                        result = data
                    break
                if status in {"FAILED", "ERROR", "CANCELLED"}:
                    raise FalImageError(f"fal generation failed: {data}")
                import time

                time.sleep(1.5)
            if result is None:
                raise FalImageError("fal generation timed out")

    images = result.get("images") or []
    if not images:
        raise FalImageError(f"fal returned no images: {result}")
    url = images[0].get("url")
    if not url:
        raise FalImageError(f"fal image missing url: {images[0]}")

    path = out_path or new_job_path("fal", "png")
    download_to(path, url)
    # sidecar meta
    path.with_suffix(".meta.json").write_text(
        __import__("json").dumps(
            {
                "provider": "fal",
                "model": FAL_FLUX_MODEL,
                "request_id": request_id,
                "prompt": prompt[:500],
                "width": width,
                "height": height,
                "seed": seed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
