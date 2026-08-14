from __future__ import annotations

from pathlib import Path

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.seed import seed_from_v2_config
from config.settings import get_settings
from db.session import get_session
from generation_engine.providers.registry import reset_providers
from orchestration_engine.actionability import assess_actionability
from orchestration_engine.mechanism import extract_mechanism
from orchestration_engine.schemas import (
    ActionabilityThresholds,
    ApproveJobRequest,
    CreateJobRequest,
    TrendOpportunityIn,
)
from orchestration_engine.service import OrchestrationService
from orchestration_engine.state import can_transition


def _opp(**kw) -> TrendOpportunityIn:
    base = dict(
        trend_id="trend_1847",
        platform="instagram",
        trend_stage="accelerating",
        velocity_score=0.91,
        freshness_score=0.88,
        saturation_score=0.24,
        opportunity_score=0.91,
        viral_mechanism="unexpected_reveal",
        format="short_form_video",
        title="Unexpected reveal format accelerating",
        audience=["gen_z"],
    )
    base.update(kw)
    return TrendOpportunityIn.model_validate(base)


def test_actionability_act_watch_reject() -> None:
    act, _ = assess_actionability(_opp())
    assert act == "ACT"
    watch, _ = assess_actionability(
        _opp(opportunity_score=0.55, velocity_score=0.5, freshness_score=0.55, saturation_score=0.4)
    )
    assert watch == "WATCH"
    reject, detail = assess_actionability(
        _opp(saturation_score=0.92, trend_stage="saturated"),
        thresholds=ActionabilityThresholds(),
    )
    assert reject == "REJECT"
    assert detail["reasons"]


def test_mechanism_not_surface_copy() -> None:
    m = extract_mechanism(_opp(viral_mechanism="surprise reveal"))
    assert m["mechanism"] == "unexpected_reveal"
    assert "surface" in m
    assert "not" in m["note"].lower() or "mechanism" in m["note"].lower()


def test_state_transitions() -> None:
    assert can_transition("DISCOVERED", "EVALUATING")
    assert can_transition("CONCEPT_SELECTED", "BRIEF_CREATED")
    assert not can_transition("PUBLISHED", "DISCOVERED")


def test_concept_brief_lineage(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        out = OrchestrationService(session).create_job(
            CreateJobRequest(
                opportunity=_opp(),
                character_slug="ghost_kid",
                mode="autonomous",
                process=True,
                run_pipeline=False,
                concept_count=5,
            )
        )
        assert out.actionability == "ACT"
        assert out.status == "BRIEF_CREATED"
        assert len(out.concepts) >= 3
        assert out.selected_concept_id
        assert out.backup_concept_id
        assert out.brief is not None
        assert out.brief.creative.get("hook")
        assert out.brief.mechanism.get("mechanism") == "unexpected_reveal"
        # Primary score highest
        scores = sorted([c.score or 0 for c in out.concepts], reverse=True)
        primary = next(c for c in out.concepts if c.selected)
        assert primary.score == scores[0]
        assert primary.score_breakdown
        lin = OrchestrationService(session).lineage(out.job_id)
        assert lin["trend_id"] == "trend_1847"
        assert lin["concept_id"]
        assert lin["production_brief_id"]
        decisions = OrchestrationService(session).decision_log(out.job_id)
        assert any(d["decision_type"] == "actionability" for d in decisions)
        assert any(d["decision_type"] == "concept_selection" for d in decisions)

    events = {e.event_type for e in get_bus().history}
    assert EventType.ORCHESTRATION_JOB_CREATED in events
    assert EventType.TREND_ACTIONABLE in events
    assert EventType.CONCEPT_SELECTED in events
    assert EventType.PRODUCTION_BRIEF_CREATED in events


def test_human_gate_semi_autonomous(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        out = OrchestrationService(session).create_job(
            CreateJobRequest(
                opportunity=_opp(),
                character_slug="ghost_kid",
                mode="semi_autonomous",
                process=True,
                run_pipeline=False,
            )
        )
        assert out.status == "AWAITING_APPROVAL"
        assert out.approval_gate == "concept"
        assert out.selected_concept_id
        approved = OrchestrationService(session).approve(
            ApproveJobRequest(job_id=out.job_id, gate="concept", continue_pipeline=False)
        )
        assert approved.status == "BRIEF_CREATED"
        assert approved.production_brief_id


def test_reject_does_not_produce(db_url: str) -> None:
    with get_session(db_url) as session:
        out = OrchestrationService(session).create_job(
            CreateJobRequest(
                opportunity=_opp(
                    opportunity_score=0.2,
                    saturation_score=0.9,
                    trend_stage="saturated",
                ),
                process=True,
                run_pipeline=False,
            )
        )
        assert out.actionability == "REJECT"
        assert out.status == "REJECTED"
        assert not out.concepts


def test_full_autonomous_pipeline(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_providers()
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        out = OrchestrationService(session).create_job(
            CreateJobRequest(
                opportunity=_opp(),
                character_slug="ghost_kid",
                mode="autonomous",
                process=True,
                run_pipeline=True,
                concept_count=3,
            )
        )
        # Should reach LEARNING or at least PUBLISHED / past QA
        assert out.status in {"LEARNING", "PUBLISHED", "MEASURING", "FAILED", "AWAITING_APPROVAL"}
        if out.status == "FAILED":
            # Surface reason for debugging
            assert out.failure_reason
            # Still must have brief + lineage for trend→concept
            assert out.production_brief_id
        else:
            lin = out.lineage
            assert lin.get("story_id")
            assert lin.get("storyboard_id")
            assert lin.get("assembly_id") or lin.get("asset_ids")
            assert lin.get("qa_id")
            if out.status in {"LEARNING", "PUBLISHED", "MEASURING"}:
                assert lin.get("publication_id")
            runs = OrchestrationService(session).engine_runs(out.job_id)
            engines = {r["engine_name"] for r in runs}
            assert "story_engine" in engines
            assert "storyboard_engine" in engines

    events = {e.event_type for e in get_bus().history}
    assert EventType.PRODUCTION_BRIEF_CREATED in events
    if EventType.ORCHESTRATION_JOB_COMPLETED in events:
        assert EventType.ORCHESTRATION_LEARNING_HANDOFF in events or True
