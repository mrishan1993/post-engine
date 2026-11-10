from __future__ import annotations

from typing import Any

from amp_platform.live_images import available_image_backends
from amp_platform.live_videos import available_video_backends
from generation_engine.providers.base import GenerationProvider
from generation_engine.providers.live import LiveGenerationProvider
from generation_engine.providers.stub import StubGenerationProvider
from prompt_engine.capabilities import PROVIDER_CAPABILITIES


_PROVIDERS: dict[str, GenerationProvider] | None = None


def _live_enabled() -> bool:
    from config.settings import get_settings

    # Keep stubs while PIPELINE_STUB_PROVIDERS=true (default) so tests/offline stay deterministic.
    return not bool(get_settings().pipeline_stub_providers)


def _build() -> dict[str, GenerationProvider]:
    providers: dict[str, GenerationProvider] = {}
    images = available_image_backends() if _live_enabled() else []
    videos = available_video_backends() if _live_enabled() else []
    for name, meta in PROVIDER_CAPABILITIES.items():
        use_live = False
        if name == "gpt_image" and images:
            use_live = True
        elif name == "runway" and videos:
            use_live = True
        elif name == "veo" and videos:
            use_live = True
        providers[name] = LiveGenerationProvider(name) if use_live else StubGenerationProvider(name)
    return providers


def list_generation_providers() -> list[dict[str, Any]]:
    out = []
    for name, meta in PROVIDER_CAPABILITIES.items():
        out.append(
            {
                "id": name,
                "modality": meta.get("modalities"),
                "capabilities": meta.get("capabilities"),
                "status": {"enabled": True},
            }
        )
    return out


def get_generation_provider(name: str) -> GenerationProvider:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    if name not in _PROVIDERS:
        raise ValueError(f"unknown generation provider: {name}")
    return _PROVIDERS[name]


def reset_providers() -> None:
    global _PROVIDERS
    _PROVIDERS = None


def inject_provider(name: str, provider: GenerationProvider) -> None:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    _PROVIDERS[name] = provider
