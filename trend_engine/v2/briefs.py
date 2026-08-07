from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ContentBrief, OpportunityScore, Vertical, ViralPrediction
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
    """Write rich character-adapted briefs into content_briefs (source=trend_engine_v2)."""
    vertical = session.scalar(select(Vertical).where(Vertical.slug == ranked.vertical_slug))
    if not vertical:
        return []

    adapted = adapt_to_characters(
        ranked.payload, characters, limit=briefs_per_opportunity
    )
    created: list[ContentBrief] = []
    brief_ids: list[int] = []
    for item in adapted:
        text = _format_brief(ranked, item)
        brief = ContentBrief(
            vertical_id=vertical.id,
            brief_text=text,
            priority=int(ranked.score / 10),
            status="pending",
            source="trend_engine_v2",
        )
        session.add(brief)
        session.flush()
        created.append(brief)
        brief_ids.append(brief.id)
        session.add(
            ViralPrediction(
                opportunity_id=opportunity_row.id,
                content_brief_id=brief.id,
                predicted_score=ranked.score,
            )
        )

    opportunity_row.content_brief_ids = brief_ids
    opportunity_row.opportunity = {
        **(opportunity_row.opportunity or {}),
        "suggested_characters": [a["character_name"] for a in adapted],
        "character_adaptations": adapted,
    }
    session.flush()
    return created


def _format_brief(ranked: RankedOpportunity, adaptation: dict[str, Any]) -> str:
    o = ranked.payload
    why = "; ".join(o.get("why_viral") or [])
    return (
        f"[V2 Opportunity score={ranked.score}] {o.get('trend')}\n"
        f"Lifecycle: {o.get('lifecycle')} | Platforms: {', '.join(o.get('platforms') or [])}\n"
        f"Emotion: {o.get('emotion')} | Pattern: {o.get('story_pattern')} | Format: {o.get('format')}\n"
        f"Character: {adaptation.get('character_name')} ({adaptation.get('character_slug')})\n"
        f"Hook: {adaptation.get('opening_line')}\n"
        f"Audio: {o.get('audio')} | Visual: {o.get('visual')} | Editing: {o.get('editing_style')}\n"
        f"Audience: {o.get('target_audience')}\n"
        f"Angle: {adaptation.get('brief_angle')}\n"
        f"Why viral: {why}\n"
        f"Publish window: next 12 hours"
    )
