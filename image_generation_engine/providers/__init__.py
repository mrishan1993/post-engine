from __future__ import annotations

from image_generation_engine.capabilities import IMAGE_PROVIDER_REGISTRY
from image_generation_engine.providers.base import ImageGenerationProvider
from image_generation_engine.providers.stub import StubImageProvider

_PROVIDERS: dict[str, ImageGenerationProvider] | None = None


def _build() -> dict[str, ImageGenerationProvider]:
    return {name: StubImageProvider(name) for name in IMAGE_PROVIDER_REGISTRY}


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
