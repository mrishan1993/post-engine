from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ProviderPerformance
from video_generation_engine.capabilities import VIDEO_PROVIDER_REGISTRY, get_video_provider_meta
from video_generation_engine.schemas import ROUTING_WEIGHTS, ProviderStrategy, VideoPromptPackage


def score_video_provider(
    session: Session,
    provider_id: str,
    package: VideoPromptPackage,
) -> dict[str, float]:
    meta = get_video_provider_meta(provider_id) or {}
    caps = meta.get("capabilities") or {}
    limits = meta.get("limits") or {}
    gen = package.generation

    capability = 1.0
    if gen.aspect_ratio not in (limits.get("supported_ratios") or []):
        capability *= 0.2
    if gen.duration_sec > float(limits.get("max_duration_sec") or 999):
        capability *= 0.3
    mode = gen.mode
    if mode == "image_to_video" and not caps.get("image_to_video"):
        capability = 0.0
    if mode == "reference_to_video" and not caps.get("character_reference"):
        capability = 0.0
    if package.references and len(package.references) > int(limits.get("max_references") or 0):
        capability *= 0.5

    perf = session.scalar(
        select(ProviderPerformance).where(
            ProviderPerformance.provider == provider_id,
            ProviderPerformance.modality == "video",
        )
    )
    historical = float(perf.avg_qa_score) if perf and perf.avg_qa_score is not None else 0.8
    reliability = float(perf.success_rate) if perf and perf.success_rate is not None else 0.9
    character = 0.95 if "character_consistency" in (meta.get("strengths") or []) else 0.75
    storyboard = 0.85
    latency = 0.85
    if perf and perf.avg_latency_ms:
        latency = max(0.3, min(1.0, 1.0 - float(perf.avg_latency_ms) / 120000))
    cps = float((meta.get("pricing") or {}).get("cost_per_sec") or 0.1)
    cost = max(0.0, min(1.0, 1.0 - cps))

    w = ROUTING_WEIGHTS
    final = (
        w["capability"] * capability
        + w["historical_quality"] * historical
        + w["character_consistency"] * character
        + w["storyboard_adherence"] * storyboard
        + w["reliability"] * reliability
        + w["latency"] * latency
        + w["cost"] * cost
    )
    return {
        "capability": round(capability, 4),
        "historical_quality": round(historical, 4),
        "character_consistency": round(character, 4),
        "storyboard_adherence": storyboard,
        "reliability": round(reliability, 4),
        "latency": round(latency, 4),
        "cost": round(cost, 4),
        "final_score": round(final, 4),
    }


def route_video_provider(
    session: Session,
    package: VideoPromptPackage,
    strategy: ProviderStrategy,
    *,
    exclude: list[str] | None = None,
) -> tuple[str, dict[str, float]]:
    exclude = exclude or []
    if strategy.mode == "locked":
        name = strategy.locked or strategy.preferred
        if not name:
            raise ValueError("locked strategy requires provider")
        return name, score_video_provider(session, name, package)

    if strategy.mode == "preferred" and strategy.preferred and strategy.preferred not in exclude:
        return strategy.preferred, score_video_provider(session, strategy.preferred, package)

    best_name = None
    best_score = None
    for name, meta in VIDEO_PROVIDER_REGISTRY.items():
        if not meta.get("enabled", True) or name in exclude:
            continue
        detail = score_video_provider(session, name, package)
        if detail["capability"] <= 0:
            continue
        if best_score is None or detail["final_score"] > best_score["final_score"]:
            best_name, best_score = name, detail
    if not best_name or not best_score:
        raise ValueError("no compatible video provider")
    return best_name, best_score


def video_fallback_chain(strategy: ProviderStrategy, primary: str) -> list[str]:
    chain = list(strategy.fallback) if strategy.fallback else [
        n for n in VIDEO_PROVIDER_REGISTRY if n != primary
    ]
    out = []
    for p in chain:
        if p != primary and p not in out:
            out.append(p)
    return out[: strategy.max_provider_switches]
