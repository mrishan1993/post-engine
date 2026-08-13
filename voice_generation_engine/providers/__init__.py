from __future__ import annotations

from voice_generation_engine.capabilities import VOICE_PROVIDER_REGISTRY
from voice_generation_engine.providers.base import VoiceGenerationProvider
from voice_generation_engine.providers.stub import StubVoiceProvider

_PROVIDERS: dict[str, VoiceGenerationProvider] | None = None


def _build() -> dict[str, VoiceGenerationProvider]:
    return {name: StubVoiceProvider(name) for name in VOICE_PROVIDER_REGISTRY}


def get_voice_provider(name: str) -> VoiceGenerationProvider:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    if name not in _PROVIDERS:
        raise ValueError(f"unknown voice provider: {name}")
    return _PROVIDERS[name]


def inject_voice_provider(name: str, provider: VoiceGenerationProvider) -> None:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    _PROVIDERS[name] = provider


def reset_voice_providers() -> None:
    global _PROVIDERS
    _PROVIDERS = None
