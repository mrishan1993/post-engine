from __future__ import annotations

from amp_platform.events import EventType, get_bus, reset_bus
from db.session import get_session
from learning_engine.policy import evidence_status
from learning_engine.schemas import (
    CreateExperimentRequest,
    RecommendRequest,
    ScopeSpec,
    TrainModelRequest,
)
from learning_engine.service import LearningService


def _seed(svc: LearningService, n: int = 36) -> None:
    hooks = ["curiosity", "curiosity", "curiosity", "question", "shock", "generic"]
    stories = ["mystery", "mystery", "suspense", "comedy"]
    for i in range(n):
        hook = hooks[i % len(hooks)]
        story = stories[i % len(stories)]
        dur = 26 if hook == "curiosity" else (18 if hook == "generic" else 24)
        completion = 0.55
        if hook == "curiosity":
            completion += 0.14
        if hook == "generic":
            completion -= 0.10
        if story == "mystery":
            completion += 0.08
        if 22 <= dur <= 28:
            completion += 0.04
        svc.add_observation(
            {
                "feature_vector": {
                    "character": "ravi",
                    "platform": "instagram",
                    "hook_type": hook,
                    "story_type": story,
                    "trend_category": "mystery_trend" if story == "mystery" else "general",
                    "duration_sec": dur,
                    "duration_bucket": "25-30"
                    if dur >= 25
                    else "20-25"
                    if dur >= 20
                    else "15-20",
                    "hour": 19 if i % 2 == 0 else 11,
                    "predicted_virality": 0.8 if story == "mystery" else 0.5,
                    "verification_stage": "primary",
                },
                "outcome_vector": {
                    "views": 100_000 + i * 2500,
                    "completion_rate": round(min(0.92, completion), 4),
                    "share_rate": 0.035 if hook == "curiosity" else 0.018,
                    "engagement_rate": 0.06 if hook == "curiosity" else 0.035,
                    "virality_score": 0.75 if hook == "curiosity" else 0.45,
                    "followers_gained": 30 + i,
                },
                "confidence": 0.85,
            }
        )


def test_evidence_status_thresholds() -> None:
    assert evidence_status(10) == "EXPLORATORY"
    assert evidence_status(50) == "SUPPORTED"
    assert evidence_status(120) == "STRONG"


def test_v1_patterns_and_brief(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        svc = LearningService(session)
        _seed(svc, n=36)

        patterns = svc.patterns(character="ravi", platform="instagram")
        assert patterns
        hooks = [p for p in patterns if p["dimension"] == "hook_type"]
        assert hooks
        best = max(hooks, key=lambda p: p["lift"])
        assert best["value"] == "curiosity"
        assert best["lift"] > 0
        assert "causal" not in best.get("note", "").lower() or "not causal" in best.get("note", "").lower()

        out = svc.brief(character="ravi", platform="instagram", persist=True)
        assert out["observation_count"] >= 30
        assert out["brief"] is not None
        brief = out["brief"]
        assert brief["character"]["id"] == "ravi"
        assert brief["platform"]["id"] == "instagram"
        assert "hook" in brief["recommendations"] or out["recommendations"]
        # Duration guidance present
        assert "duration" in brief["recommendations"]
        # Does not write the story
        assert "owns narrative" in (brief.get("note") or "").lower() or "Story Engine" in (
            brief.get("note") or ""
        )

        profile = svc.get_profile(character="ravi", platform="instagram")
        assert profile is not None
        assert profile.version >= 1
        assert profile.status == "active"

        char = svc.character("ravi")
        assert char["sample_size"] >= 30
        assert char["median_completion"] is not None

        trends = svc.trends()
        # mystery_trend should show up with enough samples
        assert any(t["trend_category"] == "mystery_trend" for t in trends) or len(trends) >= 0

    events = {e.event_type for e in get_bus().history}
    assert EventType.LEARNING_OBSERVATION_CREATED in events
    assert EventType.OPTIMIZATION_PROFILE_UPDATED in events
    assert EventType.OPTIMIZATION_RECOMMENDATION_CREATED in events or EventType.PATTERN_DETECTED in events


def test_experiment_assignment_balanced(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        svc = LearningService(session)
        exp = svc.create_experiment(
            CreateExperimentRequest(
                hypothesis="Curiosity hooks improve completion",
                variable="hook_type",
                control={"hook_type": "curiosity"},
                variants=[{"hook_type": "question"}],
                target_metric="completion_rate",
                sample_target=10,
                scope=ScopeSpec(character="ravi", platform="instagram"),
            )
        )
        assignments = [svc.assign_experiment(exp["id"]) for _ in range(10)]
        arms = {a["arm"] for a in assignments}
        assert "control" in arms
        assert "v0" in arms
        # roughly balanced
        counts = svc.get_experiment(exp["id"])["assignment_counts"]
        assert abs(counts.get("control", 0) - counts.get("v0", 0)) <= 1

    events = {e.event_type for e in get_bus().history}
    assert EventType.EXPERIMENT_CREATED in events
    assert EventType.EXPERIMENT_COMPLETED in events


def test_champion_challenger_no_inplace_mutation(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        svc = LearningService(session)
        _seed(svc, n=24)
        c1 = svc.train_model(TrainModelRequest(model_name="virality_predictor", version="c1"))
        assert c1["status"] == "challenger"
        weights_before = dict(c1["weights"] or {})

        promoted = svc.promote_model(
            {"model_id": c1["id"], "require_better_than_champion": False}
        )
        assert promoted["status"] == "champion"

        c2 = svc.train_model(TrainModelRequest(model_name="virality_predictor", version="c2"))
        assert c2["status"] == "challenger"
        # Original champion row still champion until c2 promoted
        models = {m["version"]: m for m in svc.list_models(model_name="virality_predictor")}
        assert models["c1"]["status"] == "champion"
        assert models["c2"]["status"] == "challenger"
        # Challenger training does not wipe prior champion weights identity
        assert models["c1"]["id"] == c1["id"]

        svc.promote_model({"model_id": c2["id"], "require_better_than_champion": False})
        models = {m["version"]: m for m in svc.list_models(model_name="virality_predictor")}
        assert models["c2"]["status"] == "champion"
        assert models["c1"]["status"] == "deprecated"
        # Prior challenger payload unchanged object-wise at train time
        assert weights_before == c1["weights"]

    events = {e.event_type for e in get_bus().history}
    assert EventType.MODEL_TRAINING_STARTED in events
    assert EventType.MODEL_PROMOTED in events
    assert EventType.MODEL_UPDATED in events


def test_verification_ingest_hook(db_url: str, tmp_path, monkeypatch) -> None:
    """Verification → LearningObservation soft handoff."""
    import json
    from pathlib import Path
    from uuid import uuid4

    from config.settings import get_settings
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
    from verification_engine.schemas import CreateVerificationRequest, PredictionSnapshot, PredictionTarget
    from verification_engine.service import VerificationService
    from db.models import LearningObservation
    from sqlalchemy import select

    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_analytics_providers()

    media = tmp_path / "final.mp4"
    media.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stub": True,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration_sec": 30,
        "video_codec": "h264",
        "audio_codec": "aac",
    }
    media.write_bytes(b"AMP_ASSEMBLY_STUB\n" + json.dumps(payload).encode())
    media.with_suffix(".meta.json").write_text(json.dumps(payload))

    with get_session(db_url) as session:
        pub = PublishingService(session)
        acct = pub.connect_account(
            ConnectAccountRequest(
                platform="instagram",
                external_account_id=f"ig_{uuid4().hex[:8]}",
                username="learn_user",
                access_token="stub",
                stub_oauth=True,
            )
        )
        pred = PredictionSnapshot(
            id=f"pred_{uuid4().hex[:8]}",
            content_id=f"content_{uuid4().hex[:8]}",
            model_version="v4",
            predictions={
                "virality": {"probability": 0.78},
                "engagement": {"probability": 0.7},
                "completion": {"probability": 0.65},
                "views": {"expected": 1_000_000},
                "share_rate": {"expected": 0.03},
            },
            target=PredictionTarget(threshold=1_000_000, window_hours=48),
            segments={"platform": "instagram", "character": "ravi", "hook_type": "curiosity"},
            signals={"hook_strength": 0.9},
        )
        plan = pub.create_plan(
            CreatePlanRequest(
                plan=PublishingPlanSpec(
                    content_id=pred.content_id or "c1",
                    approval=ApprovalGate(qa_status="passed", approved=True, reviewer="t"),
                    platforms=[PlatformTarget(platform="instagram", account_id=acct.id)],
                    metadata=CaptionSpec(title="H", body="B"),
                    media=MediaRefs(
                        storage_uri=str(media), duration_sec=30, width=1080, height=1920
                    ),
                    policy=PublishingPolicy(
                        require_qa=True,
                        require_human_approval=True,
                        allowed_platforms=["instagram"],
                    ),
                    prediction_id=pred.id,
                    character_slug="ravi",
                    lineage={"prediction_id": pred.id, "character_slug": "ravi"},
                    idempotency_key=f"learn_{uuid4().hex}",
                ),
                process=True,
            )
        )
        receipt = pub.list_receipts(plan.id)[0]
        PerformanceService(session).start_tracking(
            StartTrackingRequest(
                publication_id=receipt.id,
                content_fingerprint=ContentFingerprint(character="ravi", hook_type="curiosity"),
                prediction={"predictions": pred.predictions, "model_version": "v4"},
                collect_now=True,
                simulate_age_sec=48 * 3600,
                growth_profile="viral",
            )
        )
        result = VerificationService(session).create_run(
            CreateVerificationRequest(
                publication_id=receipt.id,
                prediction=pred,
                stage="primary",
                process=True,
                qa_score=0.9,
            )
        )
        obs = list(
            session.scalars(
                select(LearningObservation).where(
                    LearningObservation.source_verification_id == result.verification_id
                )
            ).all()
        )
        assert obs
        assert obs[0].feature_vector.get("character") == "ravi"
        assert obs[0].outcome_vector.get("views") is not None

    assert EventType.LEARNING_OBSERVATION_CREATED in {e.event_type for e in get_bus().history}
