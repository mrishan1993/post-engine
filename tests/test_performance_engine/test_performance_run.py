from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from amp_platform.events import EventType, get_bus, reset_bus
from config.settings import get_settings
from db.session import get_session
from performance_engine.derived import compute_derived
from performance_engine.providers import reset_analytics_providers
from performance_engine.schemas import CanonicalMetrics, ContentFingerprint, RefreshRequest, StartTrackingRequest
from performance_engine.service import PerformanceService
from performance_engine.viral import major_dropoff, transition_viral_state
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
from performance_engine.schemas import DerivedMetrics


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


def _publish_receipt(session, media: Path, *, prediction_id: str = "pred_001"):
    svc = PublishingService(session)
    acct = svc.connect_account(
        ConnectAccountRequest(
            platform="instagram",
            external_account_id=f"ig_{uuid4().hex[:8]}",
            username="perf_user",
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
                character_slug="ghost_kid",
                lineage={"prediction_id": prediction_id, "character_slug": "ghost_kid"},
                idempotency_key=f"perf_test_{uuid4().hex}",
            ),
            process=True,
        )
    )
    receipts = svc.list_receipts(plan.id)
    assert receipts
    return receipts[0]


def test_derived_metrics_and_virality_versioned() -> None:
    m = CanonicalMetrics(
        views=100_000,
        likes=6000,
        comments=400,
        shares=3500,
        saves=2000,
        followers_gained=200,
        completion_rate=0.7,
        reach=80_000,
        non_follower_reach=50_000,
        unique_viewers=82_000,
    )
    d = compute_derived(m, prev_views=40_000, prev_shares=1000, prev_velocity=50_000, delta_hours=0.5)
    assert d.engagement_formula_version == "v1"
    assert d.virality_model_version == "v1"
    assert d.share_rate == 0.035
    assert d.view_velocity_per_hour > 0
    assert 0 <= d.virality_score <= 1


def test_viral_state_machine() -> None:
    d = DerivedMetrics(
        share_rate=0.04,
        view_velocity_per_hour=130_000,
        acceleration=50_000,
    )
    assert transition_viral_state(
        "normal", derived=d, benchmark_p95_velocity=80_000, benchmark_p75_share_rate=0.03
    ) == "accelerating"
    assert (
        transition_viral_state(
            "accelerating",
            derived=d,
            benchmark_p95_velocity=80_000,
            benchmark_p75_share_rate=0.03,
        )
        == "viral"
    )


def test_dropoff_detection() -> None:
    curve = [
        {"timestamp_sec": 0, "retention_percent": 100},
        {"timestamp_sec": 3, "retention_percent": 94},
        {"timestamp_sec": 8, "retention_percent": 86},
        {"timestamp_sec": 11, "retention_percent": 62},
        {"timestamp_sec": 20, "retention_percent": 55},
    ]
    drop = major_dropoff(curve)
    assert drop and drop["timestamp"] == 11
    assert drop["severity"] == "high"


def test_v1_acceptance_timeseries_and_lineage(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_analytics_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        receipt = _publish_receipt(session, media, prediction_id="pred_loop_1")
        # Publishing auto-starts tracking; ensure more first-hour snapshots
        perf = PerformanceService(session)
        for age in (900, 1800, 3600):
            perf.refresh(
                RefreshRequest(
                    publication_id=receipt.id,
                    simulate_age_sec=age,
                    growth_profile="viral",
                )
            )
        data = perf.get_performance(receipt.id)
        assert data["prediction_id"] == "pred_loop_1"
        assert data["content_id"] == receipt.content_id
        assert data["analytics"]["views"] and data["analytics"]["views"] > 0
        assert data["analytics"]["engagement_rate"] is not None
        assert data["analytics"]["virality_score"] is not None
        assert data["analytics"]["viral_state"] in {
            "normal",
            "accelerating",
            "viral",
            "peak",
            "decelerating",
            "plateau",
            "second_wave",
        }
        assert data["lineage"] and data["lineage"].get("prediction_id") == "pred_loop_1"
        # prediction actuals filled
        pl = data["analytics"]["prediction_link"] or {}
        assert "actual" in pl

        ts = perf.get_timeseries(receipt.id, metric="views")
        assert len(ts) >= 3
        assert ts[-1]["value"] >= ts[0]["value"]

        retention = perf.get_retention(receipt.id)
        assert len(retention) >= 5
        assert retention[0]["retention_percent"] >= retention[-1]["retention_percent"]

        audience = perf.get_audience(receipt.id)
        assert audience and audience.get("demographics")

        benches = perf.get_benchmarks(receipt.id)
        assert any(b["dimension"] == "global" for b in benches)
        assert any(b.get("performance_index") is not None for b in benches)

        raw = perf.get_raw_responses(receipt.id)
        assert raw and "stub" in (raw[0]["response"] or {})

        snaps = perf.list_snapshots(receipt.id)
        assert len(snaps) >= 3
        # Raw and canonical kept separate
        assert snaps[-1].metrics and snaps[-1].raw_response_id

    events = {e.event_type for e in get_bus().history}
    assert EventType.ANALYTICS_TRACKING_STARTED in events
    assert EventType.PERFORMANCE_SNAPSHOT_CAPTURED in events
    assert EventType.PUBLICATION_VERIFIED in events


def test_manual_track_and_first_hour(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_analytics_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        receipt = _publish_receipt(session, media)
        perf = PerformanceService(session)
        # Explicit track with fingerprint
        perf.start_tracking(
            StartTrackingRequest(
                publication_id=receipt.id,
                content_fingerprint=ContentFingerprint(
                    character="ghost_kid",
                    genre="mystery",
                    hook_type="curiosity",
                    duration=30,
                ),
                prediction={"virality": 0.76, "engagement": 0.81},
                collect_now=True,
                simulate_age_sec=300,
                growth_profile="normal",
            )
        )
        perf.refresh(RefreshRequest(publication_id=receipt.id, simulate_age_sec=3600))
        data = perf.get_performance(receipt.id)
        fh = data["analytics"]["first_hour"] or {}
        assert "views_5m" in fh or "views_1h" in fh
        assert data["analytics"]["content_fingerprint"]["character"] == "ghost_kid"


def test_compare_posts(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_analytics_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        r1 = _publish_receipt(session, media, prediction_id="p1")
        r2 = _publish_receipt(session, media, prediction_id="p2")
        perf = PerformanceService(session)
        out = perf.compare({"publication_ids": [r1.id, r2.id]})
        assert len(out["posts"]) == 2
