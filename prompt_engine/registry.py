from __future__ import annotations

from typing import Any

from prompt_engine.adapters.base import ProviderAdapter
from prompt_engine.adapters.elevenlabs import ElevenLabsAdapter
from prompt_engine.adapters.gpt_image import GptImageAdapter
from prompt_engine.adapters.runway import RunwayAdapter
from prompt_engine.adapters.suno import SunoAdapter
from prompt_engine.adapters.veo import VeoAdapter
from prompt_engine.capabilities import PROVIDER_CAPABILITIES

__all__ = [
    "PROVIDER_CAPABILITIES",
    "list_providers",
    "get_capabilities",
    "get_adapter",
    "rank_providers",
    "select_provider",
]


_ADAPTERS: dict[str, ProviderAdapter] = {
    "veo": VeoAdapter(),
    "runway": RunwayAdapter(),
    "gpt_image": GptImageAdapter(),
    "elevenlabs": ElevenLabsAdapter(),
    "suno": SunoAdapter(),
}


def list_providers() -> list[dict[str, Any]]:
    return [dict(v) for v in PROVIDER_CAPABILITIES.values()]


def get_capabilities(provider: str) -> dict[str, Any] | None:
    return PROVIDER_CAPABILITIES.get(provider)


def get_adapter(provider: str) -> ProviderAdapter:
    if provider not in _ADAPTERS:
        raise ValueError(f"unknown provider adapter: {provider}")
    return _ADAPTERS[provider]


def rank_providers(modality: str, *, needs: dict[str, Any] | None = None) -> list[tuple[str, float]]:
    needs = needs or {}
    ranked: list[tuple[str, float]] = []
    for name, meta in PROVIDER_CAPABILITIES.items():
        if modality not in meta["modalities"] and not (
            modality == "thumbnail" and "image" in meta["modalities"]
        ):
            continue
        caps = meta["capabilities"]
        score = 0.7
        strengths = caps.get("strengths") or []
        if needs.get("preserve_character_identity") and "character_consistency" in strengths:
            score += 0.15
        if needs.get("camera_motion") and "camera_movement" in strengths:
            score += 0.1
        if needs.get("prefer_cost") == "low":
            cost = (
                caps.get("cost_per_sec")
                or caps.get("cost_per_image")
                or caps.get("cost_per_track")
                or 0.1
            )
            score += max(0, 0.1 - float(cost))
        limits = caps.get("limits") or {}
        max_dur = limits.get("max_duration_sec")
        if max_dur and needs.get("duration_sec") and float(needs["duration_sec"]) > float(max_dur):
            score -= 0.25
        ranked.append((name, round(min(0.99, score), 3)))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def select_provider(modality: str, preferred: str | None = None, **needs: Any) -> str:
    if preferred and preferred in PROVIDER_CAPABILITIES:
        meta = PROVIDER_CAPABILITIES[preferred]
        if modality in meta["modalities"] or (
            modality == "thumbnail" and "image" in meta["modalities"]
        ):
            return preferred
    ranked = rank_providers(modality, needs=needs)
    if not ranked:
        raise ValueError(f"no provider for modality={modality}")
    return ranked[0][0]
