from __future__ import annotations

from typing import Any

from orchestration_engine.schemas import ConceptOut, ReelProductionBrief, TrendOpportunityIn


def build_production_brief(
    *,
    content_id: str,
    opportunity: TrendOpportunityIn,
    concept: ConceptOut,
    mechanism: dict[str, Any],
    optimization_profile: dict[str, Any] | None = None,
    creative_context: dict[str, Any] | None = None,
) -> ReelProductionBrief:
    opt_recs = (optimization_profile or {}).get("recommendations") or {}
    duration = concept.estimated_duration
    if isinstance(opt_recs.get("duration"), dict):
        d = opt_recs["duration"]
        if d.get("min") and d.get("max"):
            # Prefer concept duration clamped into learned range when present
            duration = min(max(duration, int(d["min"])), int(d["max"]))

    return ReelProductionBrief(
        content_id=content_id,
        trend_id=opportunity.trend_id,
        concept_id=concept.concept_id,
        platform=opportunity.platform,
        objective=(creative_context or {}).get("objective") or "growth",
        creative={
            "hook": concept.hook,
            "story": concept.core_idea,
            "emotional_arc": concept.emotional_arc,
            "payoff": concept.audience_payoff,
            "CTA": concept.cta,
            "angle": concept.angle,
            "character_slug": concept.character_role,
        },
        visual={
            "visual_style": concept.visual_direction,
            "aspect_ratio": "9:16",
            "shot_requirements": ["hook_shot", "escalation", "reveal_or_payoff"],
            "character_requirements": [concept.character_role],
        },
        audio={
            "audio_strategy": (opportunity.audio or {}).get("audio_strategy")
            or "platform_native",
            "trend_audio": bool((opportunity.audio or {}).get("trend_audio", True)),
            "audio_type": (opportunity.audio or {}).get("type") or "platform_native_trend",
            "audio_reference": (opportunity.audio or {}).get("reference_id"),
            "voice_requirements": concept.audio_direction,
            # Do not bake rights-risky downloads into production — select at publish
            "note": (
                "platform_native + trend_audio: attach current native trend audio "
                "at publishing time; do not require copying trending audio files"
            ),
        },
        editing={
            "duration": duration,
            "pacing": mechanism.get("editing_pattern"),
            "transitions": "cut",
            "caption_style": "bottom_safe_bold",
            "loop": True,
        },
        qa_requirements={
            "character_consistency": True,
            "audio": True,
            "captions": True,
            "duration": True,
            "aspect_ratio": "9:16",
            "narrative_completeness": True,
            "platform_compliance": True,
            "first_frame_hook": True,
            "hook_without_audio": True,
        },
        publishing_requirements={
            "platform": opportunity.platform,
            "require_qa": True,
            "caption_seed": concept.hook,
            "audio_strategy": "platform_native",
            "trend_audio": True,
        },
        optimization_profile=optimization_profile,
        mechanism=mechanism,
    )
