from __future__ import annotations

import json
from pathlib import Path

from amp_platform.events import EventType, get_bus, reset_bus
from assembly_engine.schemas import (
    AssemblySpecification,
    AudioClipSpec,
    CaptionClipSpec,
    ClipSpec,
    CreateAssemblyRequest,
    DuckingSpec,
    OverlaySpec,
    SceneBlock,
)
from assembly_engine.service import AssemblyService
from config.settings import get_settings
from db.session import get_session
from publishing_engine.schemas import ApprovalGate
from publishing_engine.validation import assert_qa_gate
from publishing_engine.schemas import PublishingPlanSpec, PublishingPolicy, PlatformTarget, MediaRefs, CaptionSpec
from qa_engine.decision import decide
from qa_engine.routing import route_issue
from qa_engine.schemas import CreateQaRunRequest, QaIssueSpec, QaThresholds
from qa_engine.service import QAService
from qa_engine.state import transition_run


def _stub(path: Path, duration: float = 30.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stub": True,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration_sec": duration,
        "video_codec": "h264",
        "audio_codec": "aac",
    }
    path.write_bytes(b"AMP_ASSEMBLY_STUB\n" + json.dumps(payload).encode())
    path.with_suffix(".meta.json").write_text(json.dumps(payload))


def _make_assembly(session, tmp: Path, *, loud_music: bool = False):
    path = tmp / "final.mp4"
    _stub(path)
    return AssemblyService(session).create(
        CreateAssemblyRequest(
            specification=AssemblySpecification(
                content_id="content_qa_001",
                duration_sec=30,
                scenes=[
                    SceneBlock(scene_id="scene_001", start=0, end=10),
                    SceneBlock(scene_id="scene_002", start=10, end=20),
                    SceneBlock(scene_id="scene_003", start=20, end=30),
                ],
                video_clips=[
                    ClipSpec(
                        artifact_id="v1",
                        storage_uri=str(path),
                        start=0,
                        end=30,
                        source_end=30,
                    )
                ],
                voice_clips=[
                    AudioClipSpec(
                        artifact_id="voice_1",
                        storage_uri=str(path),
                        start=0.2,
                        end=2.6,
                        metadata={"text": "Don't open that door."},
                    )
                ],
                music_clips=[
                    AudioClipSpec(
                        artifact_id="music_1",
                        storage_uri=str(path),
                        start=0,
                        end=30,
                        volume_db=0.0 if loud_music else -12.0,
                    )
                ],
                captions=[
                    CaptionClipSpec(
                        text="DON'T OPEN THAT DOOR.",
                        start=0.2,
                        end=1.8,
                        position="bottom_safe",
                    )
                ],
                overlays=[
                    OverlaySpec(text="Follow for Part 2", start=26.5, end=30, role="cta")
                ],
                ducking=DuckingSpec(target_db=-20, bed_db=-12),
                captions_enabled=True,
            ),
            process_render=True,
        )
    )


def test_state_and_routing() -> None:
    assert transition_run("queued", "running") == "running"
    issue = route_issue(
        QaIssueSpec(code="CHARACTER_DRIFT", severity="high", message="drift")
    )
    assert issue.owner_engine == "video_generation"
    assert issue.recommended_action == "regenerate"


def test_decision_pass_and_block() -> None:
    th = QaThresholds()
    passed = decide(
        content_id="c",
        dimension_scores={
            "technical": 0.99,
            "visual": 0.93,
            "audio": 0.91,
            "character": 0.95,
            "story": 0.89,
            "storyboard": 0.92,
            "captions": 0.96,
            "platform": 1.0,
            "safety": 1.0,
            "predicted_quality": 0.87,
        },
        issues=[],
        thresholds=th,
        policy_risk="none",
    )
    assert passed.decision == "pass"
    blocked = decide(
        content_id="c",
        dimension_scores={**passed.dimensions, "safety": 0.0},
        issues=[
            QaIssueSpec(
                code="POLICY_VIOLATION",
                severity="critical",
                recommended_action="block",
                message="bad",
            )
        ],
        thresholds=th,
        policy_risk="high",
    )
    assert blocked.decision == "block"


def test_v1_pass_path(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    with get_session(db_url) as session:
        assembly = _make_assembly(session, tmp_path / "media")
        run = QAService(session).create(
            CreateQaRunRequest(
                assembly_id=assembly.id,
                process=True,
                prediction={
                    "virality_probability": 0.72,
                    "engagement_probability": 0.81,
                    "completion_probability": 0.67,
                },
            )
        )
        assert run.status == "completed"
        assert run.decision == "pass"
        assert float(run.overall_score or 0) >= 0.85
        assert run.dimension_scores
        assert "technical" in run.dimension_scores
        assert "safety" in run.dimension_scores
        issues = QAService(session).list_issues(run.id)
        # CTA/low info issues may exist; none should be high/critical
        assert not any(i.severity in {"high", "critical"} for i in issues)
        gate = QAService(session).to_publishing_approval(run.id)
        assert gate["qa_status"] == "passed"
        assert gate["approved"] is True
        # Publishing gate accepts this
        assert_qa_gate(
            PublishingPlanSpec(
                content_id=assembly.content_id,
                approval=ApprovalGate.model_validate(gate),
                platforms=[PlatformTarget(platform="instagram", account_id="x")],
                metadata=CaptionSpec(body="hi"),
                media=MediaRefs(storage_uri="unused"),
                policy=PublishingPolicy(require_qa=True, require_human_approval=True),
            )
        )

    events = {e.event_type for e in get_bus().history}
    assert EventType.QA_RUN_STARTED in events
    assert EventType.TECHNICAL_QA_COMPLETED in events
    assert EventType.SAFETY_QA_COMPLETED in events
    assert EventType.QA_RUN_COMPLETED in events


def test_regenerate_character_drift(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    with get_session(db_url) as session:
        assembly = _make_assembly(session, tmp_path / "media")
        run = QAService(session).create(
            CreateQaRunRequest(
                assembly_id=assembly.id,
                process=True,
                injected_issues=[
                    QaIssueSpec(
                        code="CHARACTER_DRIFT",
                        severity="high",
                        category="character",
                        scene_id="scene_003",
                        score=0.58,
                        message="Scene 4 face drift",
                        recommended_action="regenerate",
                    )
                ],
            )
        )
        assert run.decision == "regenerate"
        issues = QAService(session).list_issues(run.id)
        drift = next(i for i in issues if i.issue_code == "CHARACTER_DRIFT")
        assert drift.owner_engine == "video_generation"
        assert drift.scene_id == "scene_003"
        targets = (run.result or {}).get("regeneration_targets") or []
        assert targets
        assert targets[0]["owner_engine"] == "video_generation"
    assert EventType.QA_REGENERATION_REQUESTED in {e.event_type for e in get_bus().history}


def test_repair_loud_music(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    with get_session(db_url) as session:
        assembly = _make_assembly(session, tmp_path / "media", loud_music=True)
        run = QAService(session).create(
            CreateQaRunRequest(assembly_id=assembly.id, process=True)
        )
        assert run.decision == "repair"
        actions = (run.result or {}).get("repair_actions") or []
        assert any(a["code"] == "MUSIC_TOO_LOUD" for a in actions)
        assert any(a["owner_engine"] == "assembly" for a in actions)
    assert EventType.QA_REPAIR_REQUESTED in {e.event_type for e in get_bus().history}


def test_block_safety(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    with get_session(db_url) as session:
        assembly = _make_assembly(session, tmp_path / "media")
        run = QAService(session).create(
            CreateQaRunRequest(
                assembly_id=assembly.id,
                process=True,
                force_safety_risk="high",
            )
        )
        assert run.decision == "block"
        gate = QAService(session).to_publishing_approval(run.id)
        assert gate["qa_status"] == "failed"
        assert gate["approved"] is False
        assert gate["policy_risk"] == "high"


def test_missing_file_blocks(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    with get_session(db_url) as session:
        run = QAService(session).create(
            CreateQaRunRequest(
                package={
                    "content_id": "orphan",
                    "storage_uri": str(tmp_path / "nope.mp4"),
                    "duration_sec": 30,
                    "width": 1080,
                    "height": 1920,
                    "target_platforms": ["instagram"],
                },
                process=True,
            )
        )
        assert run.decision == "block"
        codes = {i.issue_code for i in QAService(session).list_issues(run.id)}
        assert "MISSING_FILE" in codes


def test_human_approve_review_required(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    with get_session(db_url) as session:
        assembly = _make_assembly(session, tmp_path / "media")
        run = QAService(session).create(
            CreateQaRunRequest(
                assembly_id=assembly.id,
                process=True,
                force_safety_risk="medium",
            )
        )
        assert run.decision == "review_required"
        assert run.status == "review_required"
        run = QAService(session).approve(run.id, reviewer="ishan")
        assert run.decision == "pass"
        assert run.status == "completed"
    assert EventType.QA_REVIEW_REQUIRED in {e.event_type for e in get_bus().history}
    assert EventType.QA_APPROVED in {e.event_type for e in get_bus().history}
