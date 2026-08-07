from __future__ import annotations

from sqlalchemy import select

from db.models import ContentBrief, ContentFeature, OpportunityScore, RawContent
from db.session import get_session
from trend_engine.v2.pipeline import answer_what_to_make, run_v2_intelligence


def test_v2_produces_opportunities_and_character_briefs(db_url: str) -> None:
    with get_session(db_url) as session:
        result = run_v2_intelligence(session, vertical="horror_narration")
        assert result.raw_content >= 1
        assert result.features == result.raw_content
        assert result.opportunities >= 1
        assert result.briefs >= 1

        feats = session.scalars(select(ContentFeature)).all()
        assert feats
        assert feats[0].hook and feats[0].emotion and feats[0].story_arc

        opps = session.scalars(select(OpportunityScore)).all()
        assert opps
        top = max(opps, key=lambda o: float(o.score))
        assert float(top.score) >= 55
        assert top.lifecycle_stage not in {"dead", "declining"}
        assert top.opportunity
        assert top.opportunity.get("hook")
        assert top.opportunity.get("suggested_characters")

        briefs = session.scalars(
            select(ContentBrief).where(ContentBrief.source == "trend_engine_v2")
        ).all()
        assert briefs
        assert any("Character:" in (b.brief_text or "") for b in briefs)
        assert any("Publish window: next 12 hours" in (b.brief_text or "") for b in briefs)


def test_what_next_answers_for_vertical(db_url: str) -> None:
    with get_session(db_url) as session:
        run_v2_intelligence(session, vertical="kids_rhymes")
        opps = answer_what_to_make(session, "kids_rhymes", limit=3)
        assert opps
        assert all(o.vertical_slug == "kids_rhymes" for o in opps)


def test_raw_content_linked_to_features(db_url: str) -> None:
    with get_session(db_url) as session:
        run_v2_intelligence(session, vertical="kids_rhymes")
        raw = session.scalars(select(RawContent)).first()
        assert raw is not None
        feat = session.scalar(
            select(ContentFeature).where(ContentFeature.raw_content_id == raw.id)
        )
        assert feat is not None
        assert feat.velocity is not None
