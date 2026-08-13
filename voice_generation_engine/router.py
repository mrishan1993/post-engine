from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ProviderPerformance, VoiceProfile
from voice_generation_engine.capabilities import VOICE_PROVIDER_REGISTRY, get_voice_provider_meta
from voice_generation_engine.registry import provider_voice_id
from voice_generation_engine.schemas import ROUTING_WEIGHTS, ProviderStrategy, VoiceSpecification


def score_voice_provider(
    session: Session,
    provider_id: str,
    spec: VoiceSpecification,
    *,
    profile: VoiceProfile | None = None,
) -> dict[str, float]:
    meta = get_voice_provider_meta(provider_id) or {}
    caps = meta.get("capabilities") or {}
    strengths = meta.get("strengths") or []

    voice_quality = 0.92 if "voice_quality" in strengths else 0.8
    character = 0.95 if "character_consistency" in strengths else 0.75
    if profile and provider_voice_id(profile, provider_id):
        character = min(1.0, character + 0.05)
    emotion = 0.95 if caps.get("emotion_control") else 0.4
    language = 0.9
    langs = caps.get("languages") or []
    if langs and spec.language not in langs and spec.language.split("-")[0] not in langs:
        language = 0.35
    pronunciation = 0.9 if caps.get("pronunciation_control") else 0.6

    perf = session.scalar(
        select(ProviderPerformance).where(
            ProviderPerformance.provider == provider_id,
            ProviderPerformance.modality == "voice",
        )
    )
    historical = float(perf.avg_qa_score) if perf and perf.avg_qa_score is not None else 0.8
    reliability = float(perf.success_rate) if perf and perf.success_rate is not None else 0.9
    latency = 0.85
    if perf and perf.avg_latency_ms:
        latency = max(0.3, min(1.0, 1.0 - float(perf.avg_latency_ms) / 60000))
    if "latency" in strengths:
        latency = max(latency, 0.9)
    cost_raw = float((meta.get("pricing") or {}).get("cost_per_1k_chars") or 0.03)
    cost = max(0.0, min(1.0, 1.0 - cost_raw * 10))

    gate = 1.0 if caps.get("text_to_speech", True) else 0.0
    if not spec.text.strip():
        gate = 0.0

    w = ROUTING_WEIGHTS
    final = (
        w["voice_quality"] * voice_quality
        + w["character_consistency"] * character
        + w["emotion_control"] * emotion
        + w["language_quality"] * language
        + w["pronunciation"] * pronunciation
        + w["historical_qa"] * historical
        + w["latency"] * latency
        + w["cost"] * cost
        + w["reliability"] * reliability
    ) * gate

    return {
        "voice_quality": round(voice_quality, 4),
        "character_consistency": round(character, 4),
        "emotion_control": round(emotion, 4),
        "language_quality": round(language, 4),
        "pronunciation": round(pronunciation, 4),
        "historical_qa": round(historical, 4),
        "latency": round(latency, 4),
        "cost": round(cost, 4),
        "reliability": round(reliability, 4),
        "final_score": round(final, 4),
    }


def route_voice_provider(
    session: Session,
    spec: VoiceSpecification,
    strategy: ProviderStrategy,
    *,
    profile: VoiceProfile | None = None,
    exclude: list[str] | None = None,
) -> tuple[str, dict[str, float]]:
    exclude = exclude or []
    if strategy.mode == "locked":
        name = strategy.locked or strategy.preferred
        if not name:
            raise ValueError("locked strategy requires provider")
        return name, score_voice_provider(session, name, spec, profile=profile)

    if strategy.mode == "preferred" and strategy.preferred and strategy.preferred not in exclude:
        return strategy.preferred, score_voice_provider(
            session, strategy.preferred, spec, profile=profile
        )

    best_name = None
    best_score = None
    for name, meta in VOICE_PROVIDER_REGISTRY.items():
        if not meta.get("enabled", True) or name in exclude:
            continue
        detail = score_voice_provider(session, name, spec, profile=profile)
        if detail["final_score"] <= 0:
            continue
        if best_score is None or detail["final_score"] > best_score["final_score"]:
            best_name, best_score = name, detail
    if not best_name or not best_score:
        raise ValueError("no compatible voice provider")
    return best_name, best_score


def voice_fallback_chain(strategy: ProviderStrategy, primary: str) -> list[str]:
    chain = list(strategy.fallback) if strategy.fallback else [
        n for n in VOICE_PROVIDER_REGISTRY if n != primary
    ]
    out = []
    for p in chain:
        if p != primary and p not in out:
            out.append(p)
    return out[: strategy.max_provider_switches]
