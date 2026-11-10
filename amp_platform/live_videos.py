"""Pick the best configured live video backend."""

from __future__ import annotations

from pathlib import Path

from amp_platform import google_veo, runway_video


class NoVideoProviderConfigured(RuntimeError):
    pass


def available_video_backends() -> list[str]:
    out = []
    if runway_video.runway_configured():
        out.append("runway")
    if google_veo.google_configured():
        out.append("google_veo")
    return out


def generate_video(
    prompt: str,
    *,
    duration_sec: float = 5.0,
    seed: int | None = None,
    image_url: str | None = None,
    out_path: Path | None = None,
    prefer: str | None = None,
) -> Path:
    order = []
    if prefer:
        order.append(prefer)
    order.extend([b for b in ("runway", "google_veo") if b not in order])

    errors: list[str] = []
    for backend in order:
        try:
            if backend == "runway" and runway_video.runway_configured():
                return runway_video.generate_video(
                    prompt,
                    duration_sec=duration_sec,
                    seed=seed,
                    image_url=image_url,
                    out_path=out_path,
                )
            if backend == "google_veo" and google_veo.google_configured():
                return google_veo.generate_video(
                    prompt,
                    duration_sec=duration_sec,
                    out_path=out_path,
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{backend}: {exc}")
            continue
    if not available_video_backends():
        raise NoVideoProviderConfigured(
            "No video API key configured. Set RUNWAY_API_KEY or GOOGLE_API_KEY."
        )
    raise RuntimeError("All video providers failed: " + " | ".join(errors))
