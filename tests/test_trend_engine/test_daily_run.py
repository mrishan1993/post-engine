from __future__ import annotations

from sqlalchemy import select

from db.models import ContentBrief
from db.session import get_session
from trend_engine.scheduler.daily_run import run_daily_ingestion


def test_daily_ingest_writes_trend_briefs(db_url: str, monkeypatch) -> None:
    monkeypatch.setenv("TREND_STUB_COLLECTORS", "true")
    from config.settings import get_settings

    get_settings.cache_clear()

    with get_session(db_url) as session:
        result = run_daily_ingestion(session)
        assert result.signals_collected >= 5
        assert result.topics_created >= 1
        assert result.briefs_created >= 1

        briefs = session.scalars(
            select(ContentBrief).where(ContentBrief.source == "trend_engine")
        ).all()
        assert briefs
        assert all(b.status == "pending" for b in briefs)
        assert all(b.priority >= 0 for b in briefs)
        # At least one vertical should have candidates
        assert result.per_vertical_candidates
