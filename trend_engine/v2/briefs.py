from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ContentBrief, OpportunityScore, Vertical, ViralPrediction
from prediction.explainability import format_explanation
from prediction.registry import PredictionRegistry
from trend_engine.v2.characters import adapt_to_characters
from trend_engine.v2.opportunity import RankedOpportunity


def generate_opportunity_briefs(
    session: Session,
    opportunity_row: OpportunityScore,
    ranked: RankedOpportunity,
    *,
    characters: list[dict[str, Any]],
    briefs_per_opportunity: int = 3,
) -> list[ContentBrief]:
    """Write character-adapted briefs + Probability Engine predictions into the registry."""
    vertical = session.scalar(select(Vertical).where(Vertical.slug == ranked.vertical_slug))
    if not vertical:
        return []

    adapted = adapt_to_characters(
        ranked.payload, characters, limit=briefs_per_opportunity
    )
    registry = PredictionRegistry(session)
    created: list[ContentBrief] = []
    brief_ids: list[int] = []
    prediction_summaries: list[dict[str, Any]] = []

    for item in adapted:
        # Predict before persisting brief priority from prediction final score
        pred_row, result = registry.predict_and_record(
            opportunity=ranked.payload,
            score_breakdown=ranked.breakdown,
            lifecycle_stage=ranked.lifecycle_stage,
            vertical_slug=ranked.vertical_slug,
            character=item,
            opportunity_id=opportunity_row.id,
            platform=(ranked.payload.get("platforms") or ["youtube"])[0],
            subsystem="probability_engine",
            decision_type="virality",
            similar_winners=int(ranked.breakdown.get("historical_success", 0.5) * 20),
        )

        text = _format_brief(ranked, item, result.reasoning_json, result)
        brief = ContentBrief(
            vertical_id=vertical.id,
            brief_text=text,
            priority=int(result.final_opportunity_score / 10),
            status="pending",
            source="trend_engine_v2",
        )
        session.add(brief)
        session.flush()

        pred_row.content_brief_id = brief.id
        created.append(brief)
        brief_ids.append(brief.id)
        session.add(
            ViralPrediction(
                opportunity_id=opportunity_row.id,
                content_brief_id=brief.id,
                predicted_score=result.final_opportunity_score,
            )
        )
        prediction_summaries.append(
            {
                "prediction_id": pred_row.id,
                "character": item.get("character_name"),
                "virality_probability": result.virality_probability,
                "expected_views": result.predicted_views,
                "confidence": result.confidence,
                "final_opportunity_score": result.final_opportunity_score,
            }
        )

    opportunity_row.content_brief_ids = brief_ids
    opportunity_row.opportunity = {
        **(opportunity_row.opportunity or {}),
        "suggested_characters": [a["character_name"] for a in adapted],
        "character_adaptations": adapted,
        "predictions": prediction_summaries,
    }
    session.flush()
    return created


def _format_brief(
    ranked: RankedOpportunity,
    adaptation: dict[str, Any],
    reasoning: dict[str, Any],
    result: Any,
) -> str:
    o = ranked.payload
    why = "; ".join(o.get("why_viral") or [])
    explain = format_explanation(reasoning)
    return (
        f"[V2+Predict score={result.final_opportunity_score}] {o.get('trend')}\n"
        f"Virality: {result.virality_probability:.0%} | "
        f"Expected views: {result.predicted_views:,} "
        f"({result.predicted_views_low:,}–{result.predicted_views_high:,}) | "
        f"Confidence: {result.confidence:.0%}\n"
        f"CTR: {result.predicted_ctr:.1%} | Watch: {result.predicted_watch_time_sec}s | "
        f"Revenue: ${result.predicted_revenue_usd:.2f} | ROI: {result.predicted_roi:.1f}x\n"
        f"Lifecycle: {o.get('lifecycle')} | Platforms: {', '.join(o.get('platforms') or [])}\n"
        f"Emotion: {o.get('emotion')} | Pattern: {o.get('story_pattern')} | Format: {o.get('format')}\n"
        f"Character: {adaptation.get('character_name')} ({adaptation.get('character_slug')})\n"
        f"Hook: {adaptation.get('opening_line')}\n"
        f"Audio: {o.get('audio')} | Visual: {o.get('visual')} | Editing: {o.get('editing_style')}\n"
        f"Audience: {o.get('target_audience')}\n"
        f"Angle: {adaptation.get('brief_angle')}\n"
        f"Why viral: {why}\n"
        f"Publish window: next 12 hours\n"
        f"---\n{explain}"
    )
