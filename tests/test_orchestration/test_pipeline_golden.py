from __future__ import annotations

import pytest

from db.models import VideoRun
from db.session import get_session
from orchestration.pipeline import Pipeline
from orchestration.state_machine import RunStatus


def test_golden_path_reaches_qa_pending(db_url: str) -> None:
    with get_session(db_url) as session:
        pipeline = Pipeline(session)
        brief = pipeline.enqueue_brief(
            "kids_rhymes",
            "learning colors with a friendly dog",
            source="manual",
        )
        run = pipeline.create_run(brief)
        pipeline.run_until_qa(run.id)
        refreshed = session.get(VideoRun, run.id)
        assert refreshed is not None
        assert refreshed.status == RunStatus.QA_PENDING.value
        assert refreshed.script_text
        assert refreshed.audio_asset_path
        assert refreshed.visual_asset_path
        assert refreshed.rendered_video_path
        assert refreshed.safety_check_result is not None
        assert float(refreshed.total_cost_usd) > 0


def test_cannot_publish_before_approval(db_url: str) -> None:
    with get_session(db_url) as session:
        pipeline = Pipeline(session)
        brief = pipeline.enqueue_brief("kids_rhymes", "counting to five")
        run = pipeline.create_run(brief)
        pipeline.run_until_qa(run.id)
        with pytest.raises(ValueError, match="qa_approved"):
            pipeline.publish(run.id)


def test_approve_then_publish(db_url: str) -> None:
    with get_session(db_url) as session:
        pipeline = Pipeline(session)
        brief = pipeline.enqueue_brief("kids_rhymes", "shapes song")
        run = pipeline.create_run(brief)
        pipeline.run_until_qa(run.id)
        pipeline.approve(run.id, reviewer="ishan")
        published = pipeline.publish(run.id)
        assert published.status == RunStatus.PUBLISHED.value
        assert published.publications


def test_reject_and_regen(db_url: str) -> None:
    with get_session(db_url) as session:
        pipeline = Pipeline(session)
        brief = pipeline.enqueue_brief("kids_rhymes", "animal sounds")
        run = pipeline.create_run(brief)
        pipeline.run_until_qa(run.id)
        pipeline.reject(run.id, reviewer="ishan", reason="mouth sync off")
        child = pipeline.regen(run.id, from_status="audio_done")
        assert child.parent_run_id == run.id
        assert child.status == RunStatus.AUDIO_DONE.value
        assert child.script_text == run.script_text
        assert child.audio_asset_path == run.audio_asset_path
        pipeline.run_until_qa(child.id)
        assert child.status == RunStatus.QA_PENDING.value
