from __future__ import annotations

from amp_platform.live_videos import available_video_backends
from video_generation_engine.capabilities import VIDEO_PROVIDER_REGISTRY
from video_generation_engine.providers.base import VideoGenerationProvider
from video_generation_engine.providers.live import LiveVideoProvider
from video_generation_engine.providers.stub import StubVideoProvider

_PROVIDERS: dict[str, VideoGenerationProvider] | None = None


def _live_enabled() -> bool:
    from config.settings import get_settings

    return not bool(get_settings().pipeline_stub_providers)


def _build() -> dict[str, VideoGenerationProvider]:
    live = available_video_backends() if _live_enabled() else []
    providers: dict[str, VideoGenerationProvider] = {}
    for name in VIDEO_PROVIDER_REGISTRY:
        if live:
            prefer = "runway" if name == "provider_b" or "runway" in live else "google_veo"
            if name == "provider_a" and "google_veo" in live:
                prefer = "google_veo"
            providers[name] = LiveVideoProvider(name, prefer=prefer)
        else:
            providers[name] = StubVideoProvider(name)
    return providers


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
