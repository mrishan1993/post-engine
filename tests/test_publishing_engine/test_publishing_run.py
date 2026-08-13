from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from amp_platform.events import EventType, get_bus, reset_bus
from config.settings import get_settings
from db.models import PublicationReceipt, PublishingJob, SocialCredential
from db.session import get_session
from publishing_engine.credentials import load_secret, store_secret
from publishing_engine.providers.stub import (
    PermanentPublishError,
    PublishBlockedError,
    StubSocialProvider,
    TransientPublishError,
)
from publishing_engine.registry import inject_provider, reset_providers
from publishing_engine.schemas import (
    ApprovalGate,
    CaptionSpec,
    ConnectAccountRequest,
    CreatePlanRequest,
    HashtagGroups,
    MediaRefs,
    PlatformTarget,
    PublishPlanRequest,
    PublishingPlanSpec,
    PublishingPolicy,
    SchedulePlanRequest,
    ScheduleSpec,
)
from publishing_engine.service import PublishingService
from publishing_engine.state import transition_job, transition_plan
from sqlalchemy import select


def _media(tmp: Path, duration: float = 30.0) -> Path:
    path = tmp / "final.mp4"
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
    return path


def _connect(svc: PublishingService, platform: str, suffix: str = "a") -> str:
    acct = svc.connect_account(
        ConnectAccountRequest(
            platform=platform,  # type: ignore[arg-type]
            external_account_id=f"{platform}_{suffix}",
            username=f"user_{platform}_{suffix}",
            access_token=f"token_{platform}_{suffix}",
            refresh_token="refresh",
            timezone="Asia/Kolkata",
            stub_oauth=True,
        )
    )
    return acct.id


def _plan_spec(
    content_id: str,
    media: Path,
    platforms: list[tuple[str, str]],
    *,
    approved: bool = True,
    qa: str = "passed",
    policy_risk: str = "none",
    force: bool = False,
) -> PublishingPlanSpec:
    return PublishingPlanSpec(
        content_id=content_id,
        approval=ApprovalGate(
            qa_status=qa,  # type: ignore[arg-type]
            approved=approved,
            policy_risk=policy_risk,  # type: ignore[arg-type]
            reviewer="tester",
        ),
        platforms=[
            PlatformTarget(platform=p, account_id=aid)  # type: ignore[arg-type]
            for p, aid in platforms
        ],
        schedule=ScheduleSpec(mode="immediate"),
        metadata=CaptionSpec(
            title="You wouldn't open this door...",
            body="Would you have opened it?",
        ),
        hashtags=HashtagGroups(broad=["#story"], niche=["#horror"]),
        media=MediaRefs(
            storage_uri=str(media),
            duration_sec=30,
            width=1080,
            height=1920,
            mime_type="video/mp4",
        ),
        policy=PublishingPolicy(
            mode="approval_required",
            require_qa=True,
            require_human_approval=True,
            allowed_platforms=[p for p, _ in platforms],  # type: ignore[arg-type]
        ),
        prediction_id="pred_001",
        lineage={"prediction_id": "pred_001"},
        force_republish=force,
        idempotency_key=f"idem_{content_id}_{uuid4().hex[:6]}",
    )


def test_state_machine() -> None:
    assert transition_plan("draft", "approved") == "approved"
    assert transition_job("queued", "validating") == "validating"
    with pytest.raises(ValueError):
        transition_job("published", "publishing")


def test_credentials_not_plaintext(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("AMP_CREDENTIALS_KEY", "test-key")
    get_settings.cache_clear()
    ref = store_secret({"access_token": "super_secret_token"})
    assert "super_secret_token" not in ref
    blob_path = tmp_path / "storage" / ".credentials" / f"{ref.removeprefix('secret://')}.bin"
    assert blob_path.exists()
    assert b"super_secret_token" not in blob_path.read_bytes()
    assert load_secret(ref)["access_token"] == "super_secret_token"


def test_v1_acceptance_instagram_youtube(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        svc = PublishingService(session)
        ig = _connect(svc, "instagram")
        yt = _connect(svc, "youtube")
        # Credential row uses reference, not raw token
        creds = list(session.scalars(select(SocialCredential)).all())
        assert creds
        assert creds[0].credential_reference.startswith("secret://")

        plan = svc.create_plan(
            CreatePlanRequest(
                plan=_plan_spec("content_001", media, [("instagram", ig), ("youtube", yt)]),
                process=True,
            )
        )
        assert plan.status == "completed"
        jobs = svc.list_jobs(plan.id)
        assert len(jobs) == 2
        assert all(j.status == "published" for j in jobs)
        receipts = svc.list_receipts(plan.id)
        assert len(receipts) == 2
        for r in receipts:
            assert r.external_post_id
            assert r.post_url
            assert r.verification_status == "verified"
            assert r.lineage and r.lineage.get("prediction_id") == "pred_001"
            out = svc.get_receipt(r.publishing_job_id)
            assert out and out.url

    events = {e.event_type for e in get_bus().history}
    assert EventType.SOCIAL_ACCOUNT_CONNECTED in events
    assert EventType.PUBLISHING_PLAN_CREATED in events
    assert EventType.MEDIA_UPLOAD_COMPLETED in events
    assert EventType.PUBLISHING_COMPLETED in events
    assert EventType.PUBLICATION_VERIFIED in events


def test_qa_gate_blocks_publish(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        svc = PublishingService(session)
        ig = _connect(svc, "instagram", "qa")
        plan = svc.create_plan(
            CreatePlanRequest(
                plan=_plan_spec(
                    "content_qa", media, [("instagram", ig)], approved=False, qa="pending"
                ),
                process=False,
            )
        )
        with pytest.raises(PublishBlockedError) as exc:
            svc.publish_plan(PublishPlanRequest(plan_id=plan.id, process=True))
        assert exc.value.reason in {"APPROVAL_REQUIRED", "QA_REQUIRED"}


def test_policy_risk_blocks(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        svc = PublishingService(session)
        ig = _connect(svc, "instagram", "risk")
        plan = svc.create_plan(
            CreatePlanRequest(
                plan=_plan_spec(
                    "content_risk",
                    media,
                    [("instagram", ig)],
                    approved=True,
                    qa="passed",
                    policy_risk="high",
                ),
                process=False,
            )
        )
        with pytest.raises(PublishBlockedError):
            svc.publish_plan(PublishPlanRequest(plan_id=plan.id, process=True))


def test_partial_success_independent_jobs(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_providers()
    inject_provider("tiktok", StubSocialProvider("tiktok", fail_permanent=True))
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        svc = PublishingService(session)
        ig = _connect(svc, "instagram", "partial")
        tt = _connect(svc, "tiktok", "partial")
        plan = svc.create_plan(
            CreatePlanRequest(
                plan=_plan_spec(
                    "content_partial",
                    media,
                    [("instagram", ig), ("tiktok", tt)],
                ),
                process=True,
            )
        )
        assert plan.status == "partial"
        jobs = {j.platform: j.status for j in svc.list_jobs(plan.id)}
        assert jobs["instagram"] == "published"
        assert jobs["tiktok"] == "failed"
        receipts = svc.list_receipts(plan.id)
        assert len(receipts) == 1
        assert receipts[0].platform == "instagram"
    reset_providers()


def test_duplicate_publish_blocked(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        svc = PublishingService(session)
        ig = _connect(svc, "instagram", "dup")
        p1 = svc.create_plan(
            CreatePlanRequest(
                plan=_plan_spec("content_dup", media, [("instagram", ig)]),
                process=True,
            )
        )
        assert p1.status == "completed"
        # Second plan same content+account — job blocked, no new receipt
        spec = _plan_spec("content_dup", media, [("instagram", ig)])
        p2 = svc.create_plan(CreatePlanRequest(plan=spec, process=False))
        p2 = svc.publish_plan(PublishPlanRequest(plan_id=p2.id, process=True))
        assert p2.status == "failed"
        jobs = svc.list_jobs(p2.id)
        assert jobs[0].status == "blocked"
        assert (jobs[0].error or {}).get("reason") == "DUPLICATE_PUBLISH_BLOCKED"
        assert len(svc.list_receipts(p2.id)) == 0


def test_invalid_media_blocked(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_providers()
    missing = tmp_path / "missing.mp4"
    with get_session(db_url) as session:
        svc = PublishingService(session)
        ig = _connect(svc, "instagram", "media")
        plan = svc.create_plan(
            CreatePlanRequest(
                plan=_plan_spec("content_media", missing, [("instagram", ig)]),
                process=False,
            )
        )
        plan = svc.publish_plan(PublishPlanRequest(plan_id=plan.id, process=True))
        assert plan.status == "failed"
        job = svc.list_jobs(plan.id)[0]
        assert job.status == "blocked"
        assert (job.error or {}).get("reason") == "INVALID_MEDIA"


def test_upload_reuse_on_publish_retry(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_providers()

    class Flaky(StubSocialProvider):
        def __init__(self):
            super().__init__("youtube")
            self.publish_calls = 0
            self.upload_calls = 0

        def upload_media(self, package, *, idempotency_key):
            self.upload_calls += 1
            return super().upload_media(package, idempotency_key=idempotency_key)

        def publish(self, package, *, external_media_id, idempotency_key):
            self.publish_calls += 1
            if self.publish_calls == 1:
                raise TransientPublishError("timeout after upload")
            return super().publish(
                package, external_media_id=external_media_id, idempotency_key=idempotency_key
            )

    flaky = Flaky()
    inject_provider("youtube", flaky)
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        svc = PublishingService(session)
        yt = _connect(svc, "youtube", "retry")
        plan = svc.create_plan(
            CreatePlanRequest(
                plan=_plan_spec("content_retry", media, [("youtube", yt)]),
                process=True,
            )
        )
        assert plan.status == "completed"
        # upload once, publish twice (fail then success)
        assert flaky.upload_calls == 1
        assert flaky.publish_calls == 2
    reset_providers()


def test_schedule_plan(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_providers()
    media = _media(tmp_path / "media")
    with get_session(db_url) as session:
        svc = PublishingService(session)
        ig = _connect(svc, "instagram", "sched")
        plan = svc.create_plan(
            CreatePlanRequest(
                plan=_plan_spec("content_sched", media, [("instagram", ig)]),
                process=False,
            )
        )
        when = datetime.now(timezone.utc) + timedelta(hours=2)
        plan = svc.schedule_plan(
            SchedulePlanRequest(plan_id=plan.id, publish_at=when, timezone="Asia/Kolkata")
        )
        assert plan.status == "scheduled"
        assert plan.schedule and plan.schedule.get("mode") == "scheduled"
    assert EventType.PUBLISHING_SCHEDULED in {e.event_type for e in get_bus().history}
