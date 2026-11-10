"""Live image generation via OpenAI Images API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from amp_platform.live_http import download_to, new_job_path, write_b64_image
from config.settings import get_settings


class OpenAIImageError(RuntimeError):
    pass


def openai_configured() -> bool:
    return bool(get_settings().openai_api_key)


def _pick_size(width: int, height: int) -> str:
    # dall-e-3 / gpt-image supported portrait-ish sizes
    if height >= width:
        return "1024x1536" if width <= 1024 else "1024x1792"
    return "1536x1024" if height <= 1024 else "1792x1024"


def generate_image(
    prompt: str,
    *,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
    out_path: Path | None = None,
    model: str | None = None,
) -> Path:
    _ = seed  # OpenAI images API may ignore seed depending on model
    settings = get_settings()
    key = settings.openai_api_key
    if not key:
        raise OpenAIImageError("OPENAI_API_KEY not configured")

    use_model = model or "gpt-image-1"
    size = _pick_size(width, height)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": use_model,
        "prompt": prompt,
        "n": 1,
        "size": size,
    }
    # gpt-image-1 returns b64 by default in many accounts; request url when supported
    if use_model.startswith("dall-e"):
        payload["response_format"] = "url"

    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        resp = client.post(
            "https://api.openai.com/v1/images/generations",
            headers=headers,
            json=payload,
        )
        if resp.status_code >= 400 and use_model == "gpt-image-1":
            # Fallback to dall-e-3
            payload["model"] = "dall-e-3"
            payload["size"] = "1024x1792" if height >= width else "1792x1024"
            payload["response_format"] = "url"
            use_model = "dall-e-3"
            resp = client.post(
                "https://api.openai.com/v1/images/generations",
                headers=headers,
                json=payload,
            )
        if resp.status_code >= 400:
            raise OpenAIImageError(f"openai images failed: {resp.status_code} {resp.text[:600]}")
        body = resp.json()

    data = (body.get("data") or [None])[0] or {}
    path = out_path or new_job_path("openai", "png")
    if data.get("b64_json"):
        write_b64_image(path, data["b64_json"])
    elif data.get("url"):
        download_to(path, data["url"])
    else:
        raise OpenAIImageError(f"openai returned no image payload: {body}")

    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "provider": "openai",
                "model": use_model,
                "prompt": prompt[:500],
                "width": width,
                "height": height,
                "size": size,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
