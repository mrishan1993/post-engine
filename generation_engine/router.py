from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ProviderPerformance
from generation_engine.schemas import ProviderStrategy
from prompt_engine.capabilities import PROVIDER_CAPABILITIES
from prompt_engine.registry import rank_providers


def score_provider(
    session: Session,
    provider: str,
    *,
    modality: str,
    prompt_package: dict[str, Any],
) -> dict[str, float]:
    meta = PROVIDER_CAPABILITIES.get(provider) or {}
    caps = meta.get("capabilities") or {}
    modality_ok = modality in (meta.get("modalities") or []) or (
        modality == "thumbnail" and "image" in (meta.get("modalities") or [])
    )
    capability = 1.0 if modality_ok else 0.0

    limits = caps.get("limits") or {}
    dur = float((prompt_package.get("parameters") or {}).get("duration_sec") or 4)
    if limits.get("max_duration_sec") and dur > float(limits["max_duration_sec"]):
        capability *= 0.3

    perf = session.scalar(
        select(ProviderPerformance).where(
            ProviderPerformance.provider == provider,
            ProviderPerformance.modality == modality,
        )
    )
    historical = float(perf.success_rate) if perf and perf.success_rate is not None else 0.85
    quality = float(perf.avg_qa_score) if perf and perf.avg_qa_score is not None else 0.8
    # cost: lower cost → higher score
    cost_unit = (
        caps.get("cost_per_sec")
        or caps.get("cost_per_image")
        or caps.get("cost_per_track")
        or 0.1
    )
    cost = max(0.0, min(1.0, 1.0 - float(cost_unit)))
    latency = 0.88
    if perf and perf.avg_latency_ms:
        latency = max(0.3, min(1.0, 1.0 - (perf.avg_latency_ms / 120_000)))
    availability = 0.99

    final = (
        0.25 * capability
        + 0.2 * quality
        + 0.2 * historical
        + 0.15 * cost
        + 0.1 * latency
        + 0.1 * availability
    )
    return {
        "capability": round(capability, 4),
        "quality": round(quality, 4),
        "historical_success": round(historical, 4),
        "cost": round(cost, 4),
        "latency": round(latency, 4),
        "availability": availability,
        "final_score": round(final, 4),
    }


def route_provider(
    session: Session,
    *,
    modality: str,
    prompt_package: dict[str, Any],
    strategy: ProviderStrategy,
    exclude: list[str] | None = None,
) -> tuple[str, dict[str, float]]:
    exclude = exclude or []

    if strategy.mode == "locked":
        name = strategy.locked or strategy.preferred
        if not name:
            raise ValueError("locked strategy requires provider")
        if name in exclude:
            raise ValueError(f"locked provider {name} excluded")
        return name, score_provider(session, name, modality=modality, prompt_package=prompt_package)

    preferred = strategy.preferred
    if strategy.mode == "preferred" and preferred and preferred not in exclude:
        return preferred, score_provider(
            session, preferred, modality=modality, prompt_package=prompt_package
        )

    # automatic — blend prompt_engine ranking with performance scores
    ranked = rank_providers(
        modality,
        needs={
            "preserve_character_identity": True,
            "duration_sec": (prompt_package.get("parameters") or {}).get("duration_sec") or 4,
            "camera_motion": True,
        },
    )
    best_name = None
    best_score: dict[str, float] | None = None
    for name, base in ranked:
        if name in exclude:
            continue
        detail = score_provider(session, name, modality=modality, prompt_package=prompt_package)
        blended = 0.5 * base + 0.5 * detail["final_score"]
        detail = {**detail, "final_score": round(blended, 4)}
        if best_score is None or detail["final_score"] > best_score["final_score"]:
            best_name, best_score = name, detail
    if not best_name or not best_score:
        raise ValueError(f"no provider available for modality={modality}")
    return best_name, best_score


def fallback_chain(strategy: ProviderStrategy, primary: str, modality: str) -> list[str]:
    chain = list(strategy.fallback)
    if not chain:
        # default from capability registry order excluding primary
        for name, meta in PROVIDER_CAPABILITIES.items():
            if name == primary:
                continue
            if modality in (meta.get("modalities") or []) or (
                modality == "thumbnail" and "image" in (meta.get("modalities") or [])
            ):
                chain.append(name)
    return [p for p in chain if p != primary][: strategy.max_provider_switches]
