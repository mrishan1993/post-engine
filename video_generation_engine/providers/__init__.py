from __future__ import annotations

from video_generation_engine.capabilities import VIDEO_PROVIDER_REGISTRY
from video_generation_engine.providers.base import VideoGenerationProvider
from video_generation_engine.providers.stub import StubVideoProvider

_PROVIDERS: dict[str, VideoGenerationProvider] | None = None


def _build() -> dict[str, VideoGenerationProvider]:
    return {name: StubVideoProvider(name) for name in VIDEO_PROVIDER_REGISTRY}


def get_video_provider(name: str) -> VideoGenerationProvider:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    if name not in _PROVIDERS:
        raise ValueError(f"unknown video provider: {name}")
    return _PROVIDERS[name]


def inject_video_provider(name: str, provider: VideoGenerationProvider) -> None:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    _PROVIDERS[name] = provider


def reset_video_providers() -> None:
    global _PROVIDERS
    _PROVIDERS = None
