from __future__ import annotations

from typing import Any

from generation_engine.providers.base import GenerationProvider
from generation_engine.providers.stub import StubGenerationProvider
from prompt_engine.capabilities import PROVIDER_CAPABILITIES


_PROVIDERS: dict[str, GenerationProvider] | None = None


def _build() -> dict[str, GenerationProvider]:
    return {name: StubGenerationProvider(name) for name in PROVIDER_CAPABILITIES}


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
