from __future__ import annotations

from image_generation_engine.capabilities import IMAGE_PROVIDER_REGISTRY
from image_generation_engine.providers.base import ImageGenerationProvider
from image_generation_engine.providers.live import LiveImageProvider
from image_generation_engine.providers.stub import StubImageProvider
from amp_platform.live_images import available_image_backends

_PROVIDERS: dict[str, ImageGenerationProvider] | None = None


def _live_enabled() -> bool:
    from config.settings import get_settings

    return not bool(get_settings().pipeline_stub_providers)


def _build() -> dict[str, ImageGenerationProvider]:
    live = available_image_backends() if _live_enabled() else []
    providers: dict[str, ImageGenerationProvider] = {}
    for name in IMAGE_PROVIDER_REGISTRY:
        if live:
            prefer = "fal" if name == "provider_a" else ("openai" if "openai" in live else live[0])
            providers[name] = LiveImageProvider(name, prefer=prefer)
        else:
            providers[name] = StubImageProvider(name)
    return providers


def get_image_provider(name: str) -> ImageGenerationProvider:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    if name not in _PROVIDERS:
        raise ValueError(f"unknown image provider: {name}")
    return _PROVIDERS[name]


def inject_image_provider(name: str, provider: ImageGenerationProvider) -> None:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    _PROVIDERS[name] = provider


def reset_image_providers() -> None:
    global _PROVIDERS
    _PROVIDERS = None
