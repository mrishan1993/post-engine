from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ProviderPerformance
from music_sfx_engine.capabilities import MUSIC_PROVIDER_REGISTRY, get_music_provider_meta
from music_sfx_engine.schemas import ROUTING_WEIGHTS, MusicSpecification, ProviderStrategy


def score_music_provider(
    session: Session,
    provider_id: str,
    spec: MusicSpecification,
) -> dict[str, float]:
    meta = get_music_provider_meta(provider_id) or {}
    caps = meta.get("capabilities") or {}
    limits = meta.get("limits") or {}

    genre_score = 1.0 if spec.genre in (caps.get("genres") or []) else 0.3
    mood_score = 0.95 if "mood_control" in (meta.get("strengths") or []) else 0.75
    instrument_control = 0.9 if caps.get("instrumental") else 0.5
    duration_score = 1.0
    if spec.duration_sec > float(limits.get("max_duration_sec") or 999):
        duration_score = 0.0
    if spec.duration_sec < float(limits.get("min_duration_sec") or 0):
        duration_score = 0.0
    stems = 1.0 if caps.get("stems") else 0.7

    perf = session.scalar(
        select(ProviderPerformance).where(
            ProviderPerformance.provider == provider_id,
            ProviderPerformance.modality == "music",
        )
    )
    historical = float(perf.avg_qa_score) if perf and perf.avg_qa_score is not None else 0.8
    reliability = float(perf.success_rate) if perf and perf.success_rate is not None else 0.9
    latency = 0.85
    if perf and perf.avg_latency_ms:
        latency = max(0.3, min(1.0, 1.0 - float(perf.avg_latency_ms) / 90000))
    if "latency" in (meta.get("strengths") or []):
        latency = max(latency, 0.9)
    cost_raw = float((meta.get("pricing") or {}).get("cost_per_generation") or 0.1)
    cost = max(0.0, min(1.0, 1.0 - cost_raw))

    capability_gate = duration_score
    if not caps.get("text_to_music", True):
        capability_gate = 0.0
    if spec.vocals_enabled and not caps.get("vocals"):
        capability_gate *= 0.2

    w = ROUTING_WEIGHTS
    final = (
        w["genre"] * genre_score
        + w["mood"] * mood_score
        + w["instrument_control"] * instrument_control
        + w["duration"] * duration_score
        + w["stems"] * stems
        + w["historical_qa"] * historical
        + w["cost"] * cost
        + w["latency"] * latency
        + w["reliability"] * reliability
    ) * (1.0 if capability_gate > 0 else 0.0)

    return {
        "genre": round(genre_score, 4),
        "mood": round(mood_score, 4),
        "instrument_control": round(instrument_control, 4),
        "duration": round(duration_score, 4),
        "stems": round(stems, 4),
        "historical_qa": round(historical, 4),
        "cost": round(cost, 4),
        "latency": round(latency, 4),
        "reliability": round(reliability, 4),
        "final_score": round(final, 4),
    }


def route_music_provider(
    session: Session,
    spec: MusicSpecification,
    strategy: ProviderStrategy,
    *,
    exclude: list[str] | None = None,
) -> tuple[str, dict[str, float]]:
    exclude = exclude or []
    if strategy.mode == "locked":
        name = strategy.locked or strategy.preferred
        if not name:
            raise ValueError("locked strategy requires provider")
        return name, score_music_provider(session, name, spec)

    if strategy.mode == "preferred" and strategy.preferred and strategy.preferred not in exclude:
        return strategy.preferred, score_music_provider(session, strategy.preferred, spec)

    best_name = None
    best_score = None
    for name, meta in MUSIC_PROVIDER_REGISTRY.items():
        if not meta.get("enabled", True) or name in exclude:
            continue
        detail = score_music_provider(session, name, spec)
        if detail["final_score"] <= 0:
            continue
        if best_score is None or detail["final_score"] > best_score["final_score"]:
            best_name, best_score = name, detail
    if not best_name or not best_score:
        raise ValueError("no compatible music provider")
    return best_name, best_score


def music_fallback_chain(strategy: ProviderStrategy, primary: str) -> list[str]:
    chain = list(strategy.fallback) if strategy.fallback else [
        n for n in MUSIC_PROVIDER_REGISTRY if n != primary
    ]
    out = []
    for p in chain:
        if p != primary and p not in out:
            out.append(p)
    return out[: strategy.max_provider_switches]
