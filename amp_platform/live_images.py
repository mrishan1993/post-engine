"""Pick the best configured live image backend."""

from __future__ import annotations

from pathlib import Path

from amp_platform import fal_images, openai_images, replicate_images


class NoImageProviderConfigured(RuntimeError):
    pass


def available_image_backends() -> list[str]:
    out = []
    if fal_images.fal_configured():
        out.append("fal")
    if openai_images.openai_configured():
        out.append("openai")
    if replicate_images.replicate_configured():
        out.append("replicate")
    return out


def generate_image(
    prompt: str,
    *,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
    out_path: Path | None = None,
    prefer: str | None = None,
) -> Path:
    order = []
    if prefer:
        order.append(prefer)
    order.extend([b for b in ("fal", "openai", "replicate") if b not in order])

    errors: list[str] = []
    for backend in order:
        try:
            if backend == "fal" and fal_images.fal_configured():
                return fal_images.generate_image(
                    prompt, width=width, height=height, seed=seed, out_path=out_path
                )
            if backend == "openai" and openai_images.openai_configured():
                return openai_images.generate_image(
                    prompt, width=width, height=height, seed=seed, out_path=out_path
                )
            if backend == "replicate" and replicate_images.replicate_configured():
                return replicate_images.generate_image(
                    prompt, width=width, height=height, seed=seed, out_path=out_path
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{backend}: {exc}")
            continue
    if not available_image_backends():
        raise NoImageProviderConfigured(
            "No image API key configured. Set FAL_KEY, OPENAI_API_KEY, or REPLICATE_API_TOKEN."
        )
    raise RuntimeError("All image providers failed: " + " | ".join(errors))
