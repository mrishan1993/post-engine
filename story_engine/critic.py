from __future__ import annotations

from story_engine.schemas import (
    CriticResult,
    ForeshadowClue,
    QualityScores,
    StoryBlueprint,
    StoryRequest,
)


def evaluate_quality(
    blueprint: StoryBlueprint,
    request: StoryRequest,
    *,
    character_fit: float = 0.9,
) -> QualityScores:
    hook = 0.7
    if blueprint.hook.hook_text and len(blueprint.hook.hook_text) > 20:
        hook += 0.1
    if blueprint.hook.type in {"warning", "pov", "curiosity_gap", "countdown", "mystery"}:
        hook += 0.08
    if blueprint.hook.duration_sec <= max(4.0, request.creative_direction.target_duration_sec * 0.15):
        hook += 0.05

    conflict = 0.65
    if blueprint.conflict.event or blueprint.conflict.events:
        conflict += 0.15
    if blueprint.stakes:
        conflict += 0.08

    curiosity = 0.6 + 0.08 * min(len(blueprint.open_loops), 4)
    if any(l.status in {"open", "escalated"} for l in blueprint.open_loops):
        curiosity += 0.1

    escalation = 0.6
    if len(blueprint.escalation.events) >= 3:
        escalation += 0.15
    if blueprint.tension_curve and blueprint.tension_curve[-2].intensity >= 0.8:
        escalation += 0.1

    payoff = 0.6
    if blueprint.twist and blueprint.twist.event:
        payoff += 0.15
    if blueprint.foreshadowing:
        payoff += 0.1
    if blueprint.ending.event:
        payoff += 0.05

    originality = 0.85
    platform_fit = 0.75
    if request.content_opportunity.platform in {
        "instagram_reels",
        "youtube_shorts",
        "tiktok",
    }:
        platform_fit += 0.1
    if blueprint.duration.estimated_seconds <= request.creative_direction.target_duration_sec + 2:
        platform_fit += 0.05

    clarity = 0.8 if blueprint.logline else 0.5
    emotional_impact = 0.7 + (
        0.15 if request.content_opportunity.emotion in {"fear", "joy"} else 0.05
    )

    scores = {
        "hook": min(hook, 0.99),
        "conflict": min(conflict, 0.99),
        "curiosity": min(curiosity, 0.99),
        "escalation": min(escalation, 0.99),
        "payoff": min(payoff, 0.99),
        "originality": originality,
        "character_fit": character_fit,
        "platform_fit": min(platform_fit, 0.99),
        "clarity": clarity,
        "emotional_impact": min(emotional_impact, 0.99),
    }
    overall = sum(scores.values()) / len(scores)
    return QualityScores(**{**scores, "overall": round(overall, 4)})


def critique_blueprint(blueprint: StoryBlueprint, request: StoryRequest) -> CriticResult:
    notes: list[str] = []
    fixes: list[str] = []

    hook_clear = bool(blueprint.hook.hook_text) and len(blueprint.hook.hook_text.split()) >= 5
    if not hook_clear:
        notes.append("Hook is vague.")
        fixes.append("Rewrite hook as a concrete warning or POV line.")

    enough_tension = any(p.intensity >= 0.8 for p in blueprint.tension_curve)
    if not enough_tension:
        notes.append("Tension never peaks high enough.")
        fixes.append("Raise late-story intensity and add one escalation beat.")

    conflict_clear = bool(blueprint.conflict.event or blueprint.conflict.events)
    escalates = len(blueprint.escalation.events) >= 3
    ending_pays_off = bool(blueprint.ending.event)

    twist_predictable = None
    if blueprint.twist:
        twist_predictable = len(blueprint.foreshadowing) == 0
        if twist_predictable:
            notes.append("Twist lacks foreshadowing.")
            fixes.append("Add 1–2 subtle foreshadowing clues.")

    cta_natural = bool(blueprint.cta.text) and "follow for more" not in (
        blueprint.cta.text or ""
    ).lower()
    if not cta_natural:
        fixes.append("Replace generic CTA with a story-specific question.")

    too_long = (
        blueprint.duration.estimated_seconds
        > request.creative_direction.target_duration_sec + 3
    )
    if too_long:
        notes.append("Estimated duration over target.")
        fixes.append("Trim escalation by one beat.")

    confusing = len(blueprint.open_loops) > 5
    would_keep = hook_clear and conflict_clear and escalates and enough_tension

    critic_score = (
        sum(
            [
                hook_clear,
                enough_tension,
                conflict_clear,
                escalates,
                ending_pays_off,
                cta_natural,
                not too_long,
                not confusing,
                twist_predictable is not True,
            ]
        )
        / 9.0
    )

    return CriticResult(
        would_keep_watching=would_keep,
        hook_clear=hook_clear,
        enough_tension=enough_tension,
        conflict_clear=conflict_clear,
        escalates=escalates,
        ending_pays_off=ending_pays_off,
        twist_predictable=twist_predictable,
        cta_natural=cta_natural,
        confusing=confusing,
        too_long=too_long,
        notes=notes,
        suggested_fixes=fixes,
        critic_score=round(critic_score, 4),
    )


def revise_blueprint(
    blueprint: StoryBlueprint,
    critic: CriticResult,
    request: StoryRequest,
) -> StoryBlueprint:
    data = blueprint.model_copy(deep=True)
    if critic.too_long and data.escalation.events:
        data.escalation.events = data.escalation.events[:-1]
        data.escalation.duration_sec = max(3.0, data.escalation.duration_sec - 2)
    if critic.twist_predictable and data.twist and not data.foreshadowing:
        data.foreshadowing = [
            ForeshadowClue(scene=1, clue="A mismatched detail appears early."),
            ForeshadowClue(scene=2, clue="A line repeats before the reveal."),
        ]
    if not critic.cta_natural:
        data.cta.text = "Would you have opened it?"
        data.cta.objective = "comments"
        data.cta.event = data.cta.text
    if not critic.enough_tension and data.tension_curve:
        data.tension_curve[-2].intensity = min(0.99, data.tension_curve[-2].intensity + 0.1)
    if not critic.hook_clear:
        data.hook.hook_text = f"Warning: {data.hook.event}"
        data.hook.type = "warning"
    parts = [
        data.hook.duration_sec,
        data.setup.duration_sec,
        data.conflict.duration_sec,
        data.escalation.duration_sec,
        data.ending.duration_sec,
        data.cta.duration_sec,
    ]
    if data.twist:
        parts.append(data.twist.duration_sec)
    data.duration.estimated_seconds = round(sum(parts), 2)
    return data
