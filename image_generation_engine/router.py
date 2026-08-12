from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ProviderPerformance
from image_generation_engine.capabilities import IMAGE_PROVIDER_REGISTRY, get_image_provider_meta
from image_generation_engine.schemas import ROUTING_WEIGHTS, ImagePromptPackage, ProviderStrategy


def score_image_provider(
    session: Session,
    provider_id: str,
    package: ImagePromptPackage,
) -> dict[str, float]:
    meta = get_image_provider_meta(provider_id) or {}
    caps = meta.get("capabilities") or {}
    limits = meta.get("limits") or {}
    gen = package.generation

    capability = 1.0
    if gen.aspect_ratio not in (limits.get("supported_ratios") or []):
        capability *= 0.2
    supported_res = limits.get("supported_resolutions") or []
    if gen.resolution and supported_res and gen.resolution not in supported_res:
        capability *= 0.5
    mode = gen.mode
    mode_checks = {
        "text_to_image": caps.get("text_to_image", True),
        "image_to_image": caps.get("image_to_image", False),
        "reference_to_image": caps.get("character_reference", False),
        "image_editing": caps.get("image_editing", False),
    }
    if not mode_checks.get(mode, True):
        capability = 0.0
    if package.references and len(package.references) > int(limits.get("max_references") or 0):
        capability *= 0.7  # will trim; soft penalty

    perf = session.scalar(
        select(ProviderPerformance).where(
            ProviderPerformance.provider == provider_id,
            ProviderPerformance.modality == "image",
        )
    )
    historical = float(perf.avg_qa_score) if perf and perf.avg_qa_score is not None else 0.8
    reliability = float(perf.success_rate) if perf and perf.success_rate is not None else 0.9
    strengths = meta.get("strengths") or []
    character = 0.95 if "character_consistency" in strengths else 0.75
    visual_quality = 0.92 if "visual_quality" in strengths else 0.8
    latency = 0.85
    if perf and perf.avg_latency_ms:
        latency = max(0.3, min(1.0, 1.0 - float(perf.avg_latency_ms) / 60000))
    if "latency" in strengths:
        latency = max(latency, 0.9)
    cpi = float((meta.get("pricing") or {}).get("cost_per_image") or 0.05)
    cost = max(0.0, min(1.0, 1.0 - cpi * 10))

    w = ROUTING_WEIGHTS
    final = (
        w["capability"] * capability
        + w["visual_quality"] * visual_quality
        + w["character_consistency"] * character
        + w["historical_qa"] * historical
        + w["reliability"] * reliability
        + w["latency"] * latency
        + w["cost"] * cost
    )
    return {
        "capability": round(capability, 4),
        "visual_quality": round(visual_quality, 4),
        "character_consistency": round(character, 4),
        "historical_qa": round(historical, 4),
        "reliability": round(reliability, 4),
        "latency": round(latency, 4),
        "cost": round(cost, 4),
        "final_score": round(final, 4),
    }


def route_image_provider(
    session: Session,
    package: ImagePromptPackage,
    strategy: ProviderStrategy,
    *,
    exclude: list[str] | None = None,
) -> tuple[str, dict[str, float]]:
    exclude = exclude or []
    if strategy.mode == "locked":
        name = strategy.locked or strategy.preferred
        if not name:
            raise ValueError("locked strategy requires provider")
        return name, score_image_provider(session, name, package)

    if strategy.mode == "preferred" and strategy.preferred and strategy.preferred not in exclude:
        return strategy.preferred, score_image_provider(session, strategy.preferred, package)

    best_name = None
    best_score = None
    for name, meta in IMAGE_PROVIDER_REGISTRY.items():
        if not meta.get("enabled", True) or name in exclude:
            continue
        detail = score_image_provider(session, name, package)
        if detail["capability"] <= 0:
            continue
        if best_score is None or detail["final_score"] > best_score["final_score"]:
            best_name, best_score = name, detail
    if not best_name or not best_score:
        raise ValueError("no compatible image provider")
    return best_name, best_score


def image_fallback_chain(strategy: ProviderStrategy, primary: str) -> list[str]:
    chain = list(strategy.fallback) if strategy.fallback else [
        n for n in IMAGE_PROVIDER_REGISTRY if n != primary
    ]
    out = []
    for p in chain:
        if p != primary and p not in out:
            out.append(p)
    return out[: strategy.max_provider_switches]
