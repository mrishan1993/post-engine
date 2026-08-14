from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from learning_engine.patterns import analyze_patterns, character_profile, trend_conversion
from learning_engine.policy import DEFAULT_POLICY
from learning_engine.recommendations import recommendations_from_patterns
from learning_engine.schemas import (
    ContentOptimizationBrief,
    OptimizationPolicy,
    OptimizationProfileOut,
    RecommendRequest,
    ScopeSpec,
)
from db.models import LearningObservation, OptimizationProfile, OptimizationRecommendation


def build_brief(
    *,
    scope: ScopeSpec,
    recommendations: list[Any],
    patterns: list[Any],
    char_profile: dict[str, Any] | None,
    exploration: dict[str, Any] | None,
    overall_confidence: float,
) -> ContentOptimizationBrief:
    rec_map: dict[str, Any] = {}
    for r in recommendations:
        data = r.model_dump() if hasattr(r, "model_dump") else r
        target = data.get("target")
        if target == "hook":
            preferred = (data.get("change") or {}).get("to")
            if preferred:
                rec_map.setdefault("hook", {}).setdefault("preferred", [])
                if preferred not in rec_map["hook"]["preferred"]:
                    rec_map["hook"]["preferred"].append(preferred)
        elif target == "story":
            rec_map["story"] = {
                "structure": (data.get("change") or {}).get("preferred_structure"),
            }
        elif target == "duration":
            ch = data.get("change") or {}
            rec_map["duration"] = {
                "target": f"{ch.get('min', 22)}-{ch.get('max', 28)}",
                "min": ch.get("min"),
                "max": ch.get("max"),
            }
        elif target == "timing":
            rec_map["timing"] = data.get("change") or {}

    # Soft defaults when data thin
    if "duration" not in rec_map and scope.character:
        rec_map["duration"] = {"target": "22-28", "min": 22, "max": 28}
    if "music" not in rec_map:
        rec_map["music"] = {"energy": "medium_low"}
    if "voice" not in rec_map:
        rec_map["voice"] = {"pace": "medium_slow"}
    if "twist" not in rec_map:
        rec_map["twist"] = {"target_seconds": "9-12"}

    evidence_summary = []
    for p in sorted(patterns, key=lambda x: -getattr(x, "lift", 0))[:8]:
        evidence_summary.append(
            p.model_dump() if hasattr(p, "model_dump") else p
        )

    return ContentOptimizationBrief(
        character={"id": scope.character, "profile": char_profile},
        platform={"id": scope.platform or "instagram"},
        trend={
            "category": scope.trend_category,
            "score": None,
        },
        recommendations=rec_map,
        exploration=exploration,
        confidence={"overall": overall_confidence},
        evidence_summary=evidence_summary,
    )


def pick_exploration(
    patterns: list[Any],
    *,
    policy: OptimizationPolicy,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """~exploration_rate chance to propose a controlled single-variable experiment hint."""
    r = rng or random.Random()
    if r.random() > policy.exploration_rate:
        return None
    hooks = [p for p in patterns if getattr(p, "dimension", None) == "hook_type"]
    if len(hooks) >= 2:
        hooks_sorted = sorted(hooks, key=lambda p: -p.lift)
        return {
            "variable": "hook_type",
            "control": hooks_sorted[0].value,
            "challenger": hooks_sorted[-1].value,
            "metric": "completion_rate",
            "rationale": "explore vs exploit — single variable",
        }
    return {
        "variable": "ending_type",
        "control": "cliffhanger",
        "challenger": "reveal",
        "metric": "completion_rate",
        "rationale": "default exploration slot",
    }


def generate_profile(
    session: Session,
    observations: list[LearningObservation],
    request: RecommendRequest,
) -> OptimizationProfileOut:
    policy = request.policy or DEFAULT_POLICY
    scope = request.scope
    patterns = analyze_patterns(observations, scope=scope)
    recs = recommendations_from_patterns(patterns, scope=scope, policy=policy)

    char_prof = None
    if scope.character:
        char_prof = character_profile(observations, scope.character)

    exploration = None
    if request.include_exploration:
        exploration = pick_exploration(patterns, policy=policy)

    # Confidence: mean of top recs or exploratory floor
    if recs:
        overall = sum(r.confidence for r in recs) / len(recs)
    else:
        overall = 0.4 if observations else 0.2
    # Cap by sample size
    n = len(observations)
    if n < policy.min_sample_size:
        overall = min(overall, 0.55)

    brief = build_brief(
        scope=scope,
        recommendations=recs,
        patterns=patterns,
        char_profile=char_prof,
        exploration=exploration,
        overall_confidence=round(overall, 3),
    )

    version = 1
    if request.persist:
        # Supersede previous active profiles with same scope keys
        prev = list(
            session.scalars(
                select(OptimizationProfile).where(OptimizationProfile.status == "active")
            ).all()
        )
        for p in prev:
            ps = p.scope or {}
            if ps.get("character") == scope.character and ps.get("platform") == scope.platform:
                p.status = "superseded"
                version = max(version, int(p.version or 1) + 1)

        profile = OptimizationProfile(
            id=str(uuid4()),
            scope=scope.model_dump(),
            recommendations=[r.model_dump() for r in recs],
            evidence={
                "patterns": [p.model_dump() for p in patterns],
                "trend_conversion": trend_conversion(observations),
                "observation_count": n,
            },
            brief=brief.model_dump(),
            confidence=overall,
            version=version,
            status="active",
            policy_snapshot=policy.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        session.add(profile)
        session.flush()

        for r in recs:
            session.add(
                OptimizationRecommendation(
                    id=r.id or str(uuid4()),
                    profile_id=profile.id,
                    scope=scope.model_dump(),
                    target=r.target,
                    action=r.action,
                    change=r.change,
                    expected_effect=r.expected_effect,
                    evidence=r.evidence,
                    confidence=r.confidence,
                    version=1,
                    status="proposed",
                )
            )
        session.flush()

        get_bus().publish(
            EventType.OPTIMIZATION_PROFILE_UPDATED,
            {
                "profile_id": profile.id,
                "version": version,
                "confidence": overall,
                "scope": scope.model_dump(),
                "recommendation_count": len(recs),
            },
            producer="learning-engine",
        )
        get_bus().publish(
            EventType.GENERATION_STRATEGY_UPDATED,
            {
                "profile_id": profile.id,
                "brief_keys": list((brief.recommendations or {}).keys()),
            },
            producer="learning-engine",
        )

        return OptimizationProfileOut(
            profile_id=profile.id,
            scope=scope,
            recommendations=recs,
            patterns=patterns,
            brief=brief,
            confidence=round(overall, 3),
            version=version,
            status="active",
            observation_count=n,
            policy=policy,
        )

    return OptimizationProfileOut(
        profile_id=f"ephemeral_{uuid4().hex[:8]}",
        scope=scope,
        recommendations=recs,
        patterns=patterns,
        brief=brief,
        confidence=round(overall, 3),
        version=0,
        status="draft",
        observation_count=n,
        policy=policy,
    )


def get_active_profile(
    session: Session,
    *,
    character: str | None = None,
    platform: str | None = None,
) -> OptimizationProfileOut | None:
    rows = list(
        session.scalars(
            select(OptimizationProfile)
            .where(OptimizationProfile.status == "active")
            .order_by(OptimizationProfile.created_at.desc())
        ).all()
    )
    for p in rows:
        s = p.scope or {}
        if character and s.get("character") != character:
            continue
        if platform and s.get("platform") != platform:
            continue
        from learning_engine.schemas import PatternStat, RecommendationOut

        pats = [PatternStat.model_validate(x) for x in (p.evidence or {}).get("patterns", [])]
        recs = [RecommendationOut.model_validate(x) for x in (p.recommendations or [])]
        brief = ContentOptimizationBrief.model_validate(p.brief) if p.brief else None
        return OptimizationProfileOut(
            profile_id=p.id,
            scope=ScopeSpec.model_validate(s),
            recommendations=recs,
            patterns=pats,
            brief=brief,
            confidence=float(p.confidence or 0),
            version=int(p.version or 1),
            status=p.status,
            observation_count=int((p.evidence or {}).get("observation_count") or 0),
            policy=OptimizationPolicy.model_validate(p.policy_snapshot)
            if p.policy_snapshot
            else DEFAULT_POLICY,
        )
    return None
