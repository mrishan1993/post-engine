from __future__ import annotations

from typing import Any
from uuid import uuid4

from amp_platform.events import EventType, get_bus
from learning_engine.policy import is_guardrail_safe
from learning_engine.schemas import (
    OptimizationPolicy,
    PatternStat,
    RecommendationOut,
    ScopeSpec,
)


def recommendations_from_patterns(
    patterns: list[PatternStat],
    *,
    scope: ScopeSpec,
    policy: OptimizationPolicy,
) -> list[RecommendationOut]:
    recs: list[RecommendationOut] = []
    # Best hook
    hooks = [p for p in patterns if p.dimension == "hook_type" and p.lift > 0.05]
    hooks.sort(key=lambda p: (-p.lift, -p.sample_size))
    if hooks:
        top = hooks[0]
        action = f"prefer_{top.value}_hooks"
        if is_guardrail_safe(action) and top.confidence >= policy.require_human_review_below * 0.5:
            recs.append(
                RecommendationOut(
                    id=f"rec_{uuid4().hex[:8]}",
                    target="hook",
                    action=action,
                    change={"to": top.value, "from": "generic"},
                    expected_effect={
                        "completion": f"+{round(top.lift * 100):.0f}% vs baseline (assoc.)",
                        "lift": top.lift,
                    },
                    confidence=top.confidence,
                    evidence={
                        "sample_size": top.sample_size,
                        "effect_size": top.lift,
                        "evidence_status": top.evidence_status,
                        "median_metric": top.median_metric,
                        "baseline_median": top.baseline_median,
                    },
                )
            )

    weak_hooks = [p for p in patterns if p.dimension == "hook_type" and p.lift < -0.1]
    weak_hooks.sort(key=lambda p: (p.lift, -p.sample_size))
    if weak_hooks:
        w = weak_hooks[0]
        action = f"reduce_{w.value}_hooks"
        if is_guardrail_safe(action):
            recs.append(
                RecommendationOut(
                    id=f"rec_{uuid4().hex[:8]}",
                    target="hook",
                    action=action,
                    change={"reduce": w.value},
                    expected_effect={"lift": w.lift},
                    confidence=w.confidence,
                    evidence={
                        "sample_size": w.sample_size,
                        "effect_size": w.lift,
                        "evidence_status": w.evidence_status,
                    },
                )
            )

    stories = [p for p in patterns if p.dimension == "story_type" and p.lift > 0.05]
    stories.sort(key=lambda p: -p.lift)
    if stories:
        s = stories[0]
        recs.append(
            RecommendationOut(
                id=f"rec_{uuid4().hex[:8]}",
                target="story",
                action=f"prefer_{s.value}_structure",
                change={"preferred_structure": s.value},
                expected_effect={"lift": s.lift},
                confidence=s.confidence,
                evidence={
                    "sample_size": s.sample_size,
                    "effect_size": s.lift,
                    "evidence_status": s.evidence_status,
                },
            )
        )

    durations = [p for p in patterns if p.dimension == "duration_bucket" and p.lift > 0]
    durations.sort(key=lambda p: -p.lift)
    if durations:
        d = durations[0]
        rng = _duration_range(d.value)
        recs.append(
            RecommendationOut(
                id=f"rec_{uuid4().hex[:8]}",
                target="duration",
                action=f"target_{d.value.replace('-', '_to_')}_seconds",
                change={"bucket": d.value, **rng},
                expected_effect={"lift": d.lift},
                confidence=d.confidence,
                evidence={
                    "sample_size": d.sample_size,
                    "effect_size": d.lift,
                    "evidence_status": d.evidence_status,
                    "scope_note": "Joint with character/story — not globally optimal",
                },
            )
        )

    hours = [p for p in patterns if p.dimension == "hour" and p.lift > 0.05]
    hours.sort(key=lambda p: -p.lift)
    if hours:
        h = hours[0]
        try:
            hour_i = int(float(h.value))
        except ValueError:
            hour_i = None
        if hour_i is not None:
            recs.append(
                RecommendationOut(
                    id=f"rec_{uuid4().hex[:8]}",
                    target="timing",
                    action="prefer_posting_window",
                    change={
                        "window": {"start": f"{hour_i:02d}:00", "end": f"{hour_i:02d}:59"},
                        "day": None,
                    },
                    expected_effect={"lift": h.lift},
                    confidence=h.confidence,
                    evidence={
                        "sample_size": h.sample_size,
                        "effect_size": h.lift,
                        "evidence_status": h.evidence_status,
                    },
                )
            )

    for rec in recs:
        get_bus().publish(
            EventType.OPTIMIZATION_RECOMMENDATION_CREATED,
            {
                "recommendation_id": rec.id,
                "target": rec.target,
                "action": rec.action,
                "confidence": rec.confidence,
                "scope": scope.model_dump(),
            },
            producer="learning-engine",
        )
    return recs


def _duration_range(bucket: str) -> dict[str, Any]:
    mapping = {
        "0-15": {"min": 0, "max": 15},
        "15-20": {"min": 15, "max": 20},
        "20-25": {"min": 20, "max": 25},
        "25-30": {"min": 25, "max": 28},
        "30-45": {"min": 30, "max": 40},
        "45+": {"min": 45, "max": 60},
    }
    return mapping.get(bucket, {"min": 22, "max": 28})
