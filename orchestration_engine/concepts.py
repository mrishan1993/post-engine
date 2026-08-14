from __future__ import annotations

from typing import Any
from uuid import uuid4

from orchestration_engine.schemas import (
    ConceptOut,
    ConceptScoreWeights,
    TrendOpportunityIn,
)


ANGLES = (
    ("personal_experience", "Character experiences the trend personally"),
    ("react_to_trend", "Character reacts to the trend"),
    ("subvert_trend", "Character subverts the trend"),
    ("relatable_application", "Character applies the trend to a relatable situation"),
    ("unexpected_version", "Character creates an unexpected version of the trend"),
)


def generate_concepts(
    *,
    opportunity: TrendOpportunityIn,
    mechanism: dict[str, Any],
    character_slug: str,
    count: int = 5,
    optimization_hints: dict[str, Any] | None = None,
) -> list[ConceptOut]:
    mech = mechanism.get("mechanism") or "curiosity_gap"
    topic = opportunity.title or mech.replace("_", " ")
    preferred_hook = None
    if optimization_hints:
        preferred_hook = ((optimization_hints.get("hook") or {}).get("preferred") or [None])[0]

    concepts: list[ConceptOut] = []
    for i, (angle, desc) in enumerate(ANGLES[: max(3, min(count, len(ANGLES)))]):
        hook = _hook_for(angle, topic, preferred_hook)
        duration = _duration_for(mechanism, angle)
        originality = round(0.72 + (i * 0.03) % 0.2, 3)
        concepts.append(
            ConceptOut(
                concept_id=f"concept_{uuid4().hex[:8]}",
                title=f"{character_slug}: {desc.split()[1]} {mech}",
                hook=hook,
                core_idea=f"{desc}. Mechanism={mech}. Topic={topic}.",
                trend_mechanism=mech,
                character_role=character_slug,
                audience_payoff=_payoff(angle, mech),
                emotional_arc=str(mechanism.get("emotional_pattern") or "curiosity → payoff"),
                visual_direction=_visual(angle),
                audio_direction="medium_low energy bed; dialogue-forward"
                if preferred_hook
                else "match emotional_pattern pacing",
                estimated_duration=duration,
                cta="Follow for Part 2" if angle != "subvert_trend" else "Would you have done this?",
                originality_score=originality,
                angle=angle,
            )
        )
    return concepts


def score_concept(
    concept: ConceptOut,
    *,
    opportunity: TrendOpportunityIn,
    mechanism: dict[str, Any],
    character_slug: str,
    weights: ConceptScoreWeights | None = None,
    historical_boost: float = 0.0,
) -> ConceptOut:
    w = weights or ConceptScoreWeights()
    mech = mechanism.get("mechanism") or ""
    dims = {
        "trend_fit": 0.85 if concept.trend_mechanism == mech else 0.55,
        "hook_strength": min(1.0, 0.55 + concept.originality_score * 0.4),
        "audience_fit": 0.8 if opportunity.audience else 0.65,
        "character_fit": 0.9 if concept.character_role == character_slug else 0.5,
        "novelty": concept.originality_score,
        "retention_potential": 0.85 if 8 <= concept.estimated_duration <= 28 else 0.6,
        "shareability": 0.88 if concept.angle in {"unexpected_version", "subvert_trend", "personal_experience"} else 0.7,
        "production_feasibility": 0.9 if concept.estimated_duration <= 30 else 0.65,
        "platform_fit": 0.9 if opportunity.platform in {"instagram", "tiktok", "youtube"} else 0.7,
    }
    # Angle priors for unexpected_reveal
    if mech == "unexpected_reveal" and concept.angle == "unexpected_version":
        dims["shareability"] = min(1.0, dims["shareability"] + 0.08)
        dims["retention_potential"] = min(1.0, dims["retention_potential"] + 0.06)
    if historical_boost:
        for k in dims:
            dims[k] = min(1.0, dims[k] + historical_boost * 0.05)

    score = (
        dims["trend_fit"] * w.trend_fit
        + dims["hook_strength"] * w.hook_strength
        + dims["audience_fit"] * w.audience_fit
        + dims["character_fit"] * w.character_fit
        + dims["novelty"] * w.novelty
        + dims["retention_potential"] * w.retention_potential
        + dims["shareability"] * w.shareability
        + dims["production_feasibility"] * w.production_feasibility
        + dims["platform_fit"] * w.platform_fit
    )
    concept.score = round(score, 4)
    concept.score_breakdown = {k: round(v, 4) for k, v in dims.items()}
    return concept


def select_concepts(concepts: list[ConceptOut]) -> tuple[ConceptOut, ConceptOut | None, list[ConceptOut]]:
    ranked = sorted(concepts, key=lambda c: float(c.score or 0), reverse=True)
    if not ranked:
        raise ValueError("no concepts to select")
    primary = ranked[0]
    primary.selected = True
    backup = ranked[1] if len(ranked) > 1 else None
    if backup:
        backup.is_backup = True
    rejected = []
    for c in ranked[2:] if backup else ranked[1:]:
        c.rejection_reason = f"score={c.score} below primary/backup"
        rejected.append(c)
    # Also mark non-selected non-backup in full list
    if backup:
        for c in ranked[2:]:
            c.selected = False
            c.is_backup = False
    return primary, backup, rejected


def _hook_for(angle: str, topic: str, preferred: str | None) -> str:
    if preferred == "curiosity" or preferred == "curiosity_gap":
        return f"Wait — you won't believe what happens with {topic}…"
    hooks = {
        "personal_experience": f"I tried {topic} and it went wrong…",
        "react_to_trend": f"Everyone's doing {topic}. Here's my honest reaction.",
        "subvert_trend": f"They want you to copy {topic}. Don't.",
        "relatable_application": f"POV: {topic} but it's your actual life.",
        "unexpected_version": f"You think this is about {topic}. It's not.",
    }
    return hooks.get(angle, f"Watch this {topic} twist.")


def _payoff(angle: str, mech: str) -> str:
    return f"Audience gets a {mech.replace('_', ' ')} payoff via {angle.replace('_', ' ')}"


def _visual(angle: str) -> str:
    return {
        "personal_experience": "POV close-ups, handheld urgency",
        "react_to_trend": "reaction cutaways + trend reference framing",
        "subvert_trend": "misdirect establishing shot then hard cut",
        "relatable_application": "everyday setting, recognition framing",
        "unexpected_version": "setup looks normal → reveal reframes everything",
    }.get(angle, "cinematic short-form")


def _duration_for(mechanism: dict[str, Any], angle: str) -> int:
    rec = str(mechanism.get("recommended_duration") or "12-25s")
    try:
        parts = rec.replace("s", "").split("-")
        lo, hi = int(parts[0]), int(parts[1])
        mid = (lo + hi) // 2
    except Exception:  # noqa: BLE001
        lo, hi, mid = 8, 15, 12
    if angle == "unexpected_version":
        return min(hi, mid + 2)
    if angle == "subvert_trend":
        return max(lo, mid - 2)
    return mid
