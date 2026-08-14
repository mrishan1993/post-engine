from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from amp_platform.events import EventType, get_bus, reset_bus
from config.settings import get_settings
from db.models import VerificationRun
from db.session import get_session
from performance_engine.providers import reset_analytics_providers
from performance_engine.schemas import ContentFingerprint, StartTrackingRequest
from performance_engine.service import PerformanceService
from publishing_engine.schemas import (
    ApprovalGate,
    CaptionSpec,
    ConnectAccountRequest,
    CreatePlanRequest,
    MediaRefs,
    PlatformTarget,
    PublishingPlanSpec,
    PublishingPolicy,
)
from publishing_engine.service import PublishingService
from verification_engine.calibration import probability_bucket
from verification_engine.metrics import absolute_error, log_error, relative_error, verify_metric
from verification_engine.schemas import CreateVerificationRequest, PredictionSnapshot, PredictionTarget
from verification_engine.service import VerificationService


def _media(tmp: Path) -> Path:
    path = tmp / "final.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stub": True,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration_sec": 30,
        "video_codec": "h264",
        "audio_codec": "aac",
    }
    path.write_bytes(b"AMP_ASSEMBLY_STUB\n" + json.dumps(payload).encode())
    path.with_suffix(".meta.json").write_text(json.dumps(payload))
    return path


def _publish(session, media: Path, *, prediction_id: str):
    svc = PublishingService(session)
    acct = svc.connect_account(
        ConnectAccountRequest(
            platform="instagram",
            external_account_id=f"ig_{uuid4().hex[:8]}",
            username="verify_user",
            access_token="stub",
            stub_oauth=True,
        )
    )
    plan = svc.create_plan(
        CreatePlanRequest(
            plan=PublishingPlanSpec(
                content_id=f"content_{uuid4().hex[:8]}",
                approval=ApprovalGate(qa_status="passed", approved=True, reviewer="test"),
                platforms=[PlatformTarget(platform="instagram", account_id=acct.id)],
                metadata=CaptionSpec(title="Hook", body="Would you open it?"),
                media=MediaRefs(
                    storage_uri=str(media),
                    duration_sec=30,
                    width=1080,
                    height=1920,
                ),
                policy=PublishingPolicy(
                    require_qa=True,
                    require_human_approval=True,
                    allowed_platforms=["instagram"],
                ),
                prediction_id=prediction_id,
                character_slug="ravi",
                lineage={"prediction_id": prediction_id, "character_slug": "ravi"},
                idempotency_key=f"verify_test_{uuid4().hex}",
            ),
            process=True,
        )
    )
    return svc.list_receipts(plan.id)[0]


def _snapshot(**overrides) -> PredictionSnapshot:
    base = PredictionSnapshot(
        id=f"pred_{uuid4().hex[:8]}",
        content_id=f"content_{uuid4().hex[:8]}",
        model_id="virality_predictor",
        model_version="v4",
        predictions={
            "virality": {"probability": 0.78},
            "engagement": {"probability": 0.72},
            "completion": {"probability": 0.65},
            "share_rate": {"expected": 0.034},
            "views": {"expected": 1_000_000},
        },
        confidence={"overall": 0.81},
        target=PredictionTarget(metric="views", threshold=1_000_000, window_hours=48),
        signals={"hook_strength": 0.88, "trend_velocity": 0.91},
        segments={"platform": "instagram", "character": "ravi", "hook_type": "curiosity"},
    )
    return base.model_copy(update=overrides)


def test_error_metrics_unit() -> None:
    assert absolute_error(1_000_000, 2_400_000) == 1_400_000
    assert relative_error(1_000_000, 2_400_000) == 1.4
    assert log_error(1_000_000, 2_400_000) > 0
    mv = verify_metric("views", 1_000_000, 2_400_000)
    assert mv.absolute_error == 1_400_000
    assert mv.relative_error == 1.4
    assert probability_bucket(0.78) == "0.7-0.8"


def test_v1_binary_and_continuous_verification(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_analytics_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        pred = _snapshot()
        receipt = _publish(session, media, prediction_id=pred.id)
        PerformanceService(session).start_tracking(
            StartTrackingRequest(
                publication_id=receipt.id,
                content_fingerprint=ContentFingerprint(character="ravi", hook_type="curiosity"),
                prediction={
                    "model_id": pred.model_id,
                    "model_version": pred.model_version,
                    "predictions": pred.predictions,
                    "target": pred.target.model_dump(),
                    "signals": pred.signals,
                    "confidence": 0.81,
                },
                collect_now=True,
                simulate_age_sec=48 * 3600,
                growth_profile="viral",
            )
        )
        # Immutable snapshot: store then verify we don't mutate the input object fields
        snap_before = pred.model_dump(mode="json")
        result = VerificationService(session).create_run(
            CreateVerificationRequest(
                publication_id=receipt.id,
                prediction=pred,
                stage="primary",
                process=True,
                qa_score=0.9,
            )
        )
        assert pred.model_dump(mode="json") == snap_before

        views_row = next(m for m in result.metrics if m.metric == "views")
        assert views_row.predicted_value == 1_000_000
        assert views_row.actual_value and views_row.actual_value > 1_000_000
        assert views_row.absolute_error == absolute_error(
            views_row.predicted_value, views_row.actual_value
        )
        assert views_row.relative_error and views_row.relative_error > 0

        viral = next(m for m in result.metrics if m.metric == "viral_target")
        assert viral.outcome is True
        assert viral.predicted_value == 0.78
        assert result.brier_score is not None
        assert result.status in {"verified", "early_result"}
        assert any(s.signal_type == "prediction_error_vector" for s in result.learning_signals)
        assert result.diagnosis is not None
        assert "causal" not in (result.diagnosis.note or "").lower() or "not causal" in (
            result.diagnosis.note or ""
        ).lower()

        run = session.get(VerificationRun, result.verification_id)
        assert run is not None
        assert run.prediction_snapshot["predictions"]["virality"]["probability"] == 0.78

        pred2 = PredictionSnapshot.model_validate(snap_before)
        result2 = VerificationService(session).create_run(
            CreateVerificationRequest(
                publication_id=receipt.id,
                prediction=pred2,
                stage="long_term",
                process=True,
                actuals={"views": 420_000, "engagement_rate": 0.02, "completion_rate": 0.4},
                qa_score=0.9,
            )
        )
        fail = next(m for m in result2.metrics if m.metric == "viral_target")
        assert fail.outcome is False
        assert result2.confidence_label in {"overconfident", "incorrect"}
        # Original run snapshot still 0.78 (never overwritten by later runs)
        session.refresh(run)
        assert run.prediction_snapshot["predictions"]["virality"]["probability"] == 0.78

    events = {e.event_type for e in get_bus().history}
    assert EventType.VERIFICATION_STARTED in events
    assert EventType.PRIMARY_VERIFICATION_COMPLETED in events or EventType.LONG_TERM_VERIFICATION_COMPLETED in events
    assert EventType.LEARNING_SIGNAL_CREATED in events
    assert EventType.CALIBRATION_UPDATED in events


def test_calibration_buckets_accumulate(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_analytics_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        for i, (p, views) in enumerate([(0.78, 1_400_000), (0.75, 1_200_000), (0.72, 420_000)]):
            pred = _snapshot(
                id=f"pred_cal_{i}",
                predictions={
                    "virality": {"probability": p},
                    "engagement": {"probability": 0.7},
                    "completion": {"probability": 0.6},
                    "share_rate": {"expected": 0.03},
                    "views": {"expected": 1_000_000},
                },
            )
            receipt = _publish(session, media, prediction_id=pred.id)
            VerificationService(session).create_run(
                CreateVerificationRequest(
                    publication_id=receipt.id,
                    prediction=pred,
                    stage="primary",
                    process=True,
                    actuals={"views": views, "virality_score": 0.8 if views > 1e6 else 0.3},
                )
            )
        buckets = VerificationService(session).calibration(
            "virality_predictor", model_version="v4", metric="viral_target"
        )
        global_buckets = [b for b in buckets if b["segment_key"] == "global"]
        assert global_buckets
        # 0.7-0.8 bucket should have samples
        b78 = next(b for b in global_buckets if b["probability_bucket"] == "0.7-0.8")
        assert b78["sample_count"] >= 3
        assert b78["actual_success_rate"] is not None
        # 2 successes / 3 → ~0.666, mean_p ~0.75 → calibration_error ≈ actual - mean
        assert abs(b78["actual_success_rate"] - (2 / 3)) < 0.01

        signals = VerificationService(session).learning_signals(limit=20)
        assert any(s["signal_type"] == "segment_calibration_hint" for s in signals) or any(
            s["signal_type"] == "prediction_error_vector" for s in signals
        )


def test_windowed_target_not_confused_with_late_virality(
    db_url: str, tmp_path: Path, monkeypatch
) -> None:
    """Verification uses the measurement window actuals provided — not 'eventually'."""
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_analytics_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        pred = _snapshot()
        receipt = _publish(session, media, prediction_id=pred.id)
        # Force 48h-window miss even if later growth would succeed
        result = VerificationService(session).create_run(
            CreateVerificationRequest(
                publication_id=receipt.id,
                prediction=pred,
                stage="primary",
                process=True,
                actuals={
                    "views": 420_000,
                    "engagement_rate": 0.02,
                    "completion_rate": 0.5,
                    "share_rate": 0.01,
                },
                measurement_window_hours=48,
            )
        )
        viral = next(m for m in result.metrics if m.metric == "viral_target")
        assert viral.outcome is False
        assert viral.actual_value == 420_000
