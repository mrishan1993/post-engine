from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ContentBrief, Prediction


def rank_briefs_for_production(
    session: Session,
    *,
    vertical_slug: str | None = None,
    min_virality: float = 0.55,
    min_confidence: float = 0.45,
    min_final_score: float = 50,
    limit: int = 10,
) -> list[tuple[ContentBrief, Prediction]]:
    """Only top-ranked predicted opportunities should enter production."""
    q = (
        select(Prediction, ContentBrief)
        .join(ContentBrief, ContentBrief.id == Prediction.content_brief_id)
        .where(
            ContentBrief.status == "pending",
            Prediction.decision_type == "virality",
            Prediction.virality_probability >= min_virality,
            Prediction.confidence >= min_confidence,
            Prediction.final_opportunity_score >= min_final_score,
        )
        .order_by(Prediction.final_opportunity_score.desc())
        .limit(limit)
    )
    if vertical_slug:
        q = q.where(Prediction.vertical_slug == vertical_slug)

    rows = session.execute(q).all()
    return [(brief, pred) for pred, brief in rows]
