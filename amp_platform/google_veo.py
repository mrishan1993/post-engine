"""Live video generation via Google Veo (Gemini API long-running)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from amp_platform.live_http import download_to, new_job_path
from config.settings import get_settings

VEO_MODEL = "veo-2.0-generate-001"


class GoogleVeoError(RuntimeError):
    pass


def google_configured() -> bool:
    return bool(get_settings().google_api_key)


def generate_video(
    prompt: str,
    *,
    duration_sec: float = 5.0,
    aspect_ratio: str = "9:16",
    out_path: Path | None = None,
) -> Path:
    key = get_settings().google_api_key
    if not key:
        raise GoogleVeoError("GOOGLE_API_KEY not configured")

    # Veo via Generative Language API (predictLongRunning)
    start_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{VEO_MODEL}"
        f":predictLongRunning?key={key}"
    )
    # API expects duration as enum-ish seconds in some versions; keep integer 5–8
    dur = int(max(5, min(8, round(duration_sec))))
    payload: dict[str, Any] = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": dur,
        },
    }

    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        submit = client.post(start_url, json=payload)
        if submit.status_code >= 400:
            raise GoogleVeoError(f"veo submit failed: {submit.status_code} {submit.text[:700]}")
        body = submit.json()
        op_name = body.get("name")
        if not op_name:
            raise GoogleVeoError(f"veo missing operation name: {body}")

        op_url = f"https://generativelanguage.googleapis.com/v1beta/{op_name}?key={key}"
        result = None
        for _ in range(120):
            st = client.get(op_url)
            st.raise_for_status()
            data = st.json()
            if data.get("done"):
                if data.get("error"):
                    raise GoogleVeoError(f"veo failed: {data['error']}")
                result = data
                break
            time.sleep(5)
        if result is None:
            raise GoogleVeoError("veo timed out")

    # Extract URI from response variants
    resp = result.get("response") or {}
    generate = resp.get("generateVideoResponse") or resp
    samples = (
        generate.get("generatedSamples")
        or generate.get("videos")
        or generate.get("generatedVideos")
        or []
    )
    url = None
    if samples:
        sample = samples[0]
        video = sample.get("video") or sample
        url = video.get("uri") or video.get("url")
    if not url:
        # Some payloads nest under predictions
        preds = resp.get("predictions") or []
        if preds:
            bytes_b64 = preds[0].get("bytesBase64Encoded")
            if bytes_b64:
                import base64

                path = out_path or new_job_path("veo", "mp4")
                path.write_bytes(base64.b64decode(bytes_b64))
                path.with_suffix(".meta.json").write_text(
                    json.dumps({"provider": "google_veo", "model": VEO_MODEL, "prompt": prompt[:500]}, indent=2),
                    encoding="utf-8",
                )
                return path
        raise GoogleVeoError(f"veo returned no video uri: {result}")

    path = out_path or new_job_path("veo", "mp4")
    download_to(path, str(url), headers={"x-goog-api-key": key} if "generativelanguage" in str(url) else None)
    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "provider": "google_veo",
                "model": VEO_MODEL,
                "prompt": prompt[:500],
                "duration_sec": dur,
                "aspect_ratio": aspect_ratio,
                "operation": op_name,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
