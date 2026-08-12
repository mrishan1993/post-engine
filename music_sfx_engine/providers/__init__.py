from __future__ import annotations

from music_sfx_engine.capabilities import MUSIC_PROVIDER_REGISTRY
from music_sfx_engine.providers.base import MusicGenerationProvider
from music_sfx_engine.providers.stub import StubMusicProvider

_PROVIDERS: dict[str, MusicGenerationProvider] | None = None


def _build() -> dict[str, MusicGenerationProvider]:
    return {name: StubMusicProvider(name) for name in MUSIC_PROVIDER_REGISTRY}


def get_music_provider(name: str) -> MusicGenerationProvider:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    if name not in _PROVIDERS:
        raise ValueError(f"unknown music provider: {name}")
    return _PROVIDERS[name]


def inject_music_provider(name: str, provider: MusicGenerationProvider) -> None:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    _PROVIDERS[name] = provider


def reset_music_providers() -> None:
    global _PROVIDERS
    _PROVIDERS = None
