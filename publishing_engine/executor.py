from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from publishing_engine.credentials import load_secret, store_secret
from publishing_engine.package_builder import (
    build_platform_package,
    validate_media_against_profile,
)
from publishing_engine.providers.stub import (
    PermanentPublishError,
    PublishBlockedError,
    TransientPublishError,
)
from publishing_engine.registry import get_provider
from publishing_engine.schemas import PublishingPlanSpec
from publishing_engine.state import transition_job, transition_plan
from publishing_engine.validation import (
    assert_account_ready,
    assert_not_duplicate,
    assert_platform_allowed,
    assert_qa_gate,
    assert_rate_limit,
)
from db.models import (
    PublicationReceipt,
    PublishingJob,
    PublishingPlan,
    SocialCredential,
)

MAX_ATTEMPTS = 4


class PublishingExecutor:
    def __init__(self, session: Session):
        self.session = session

    def process_plan(self, plan_id: str, *, force: bool = False) -> PublishingPlan:
        plan = self.session.get(PublishingPlan, plan_id)
        if not plan:
            raise ValueError("publishing plan not found")
        spec = PublishingPlanSpec.model_validate(
            {
                "content_id": plan.content_id,
                "approval": plan.approval or {},
                "platforms": plan.platforms or [],
                "schedule": plan.schedule or {"mode": "immediate"},
                "metadata": (plan.metadata_json or {}).get("caption")
                or plan.metadata_json
                or {},
                "hashtags": (plan.metadata_json or {}).get("hashtags") or {},
                "media": (plan.metadata_json or {}).get("media") or {
                    "master_artifact_id": plan.master_artifact_id,
                    "cover_artifact_id": plan.cover_artifact_id,
                    **((plan.metadata_json or {}).get("media_refs") or {}),
                },
                "policy": plan.policy or {},
                "assembly_id": plan.assembly_id,
                "lineage": plan.lineage or {},
                "force_republish": force,
                **{
                    k: (plan.lineage or {}).get(k)
                    for k in ("prediction_id", "story_id", "storyboard_id", "character_slug")
                    if (plan.lineage or {}).get(k)
                },
            }
        )
        # Reconstruct metadata properly from stored shape
        meta = plan.metadata_json or {}
        if "body" in meta or "title" in meta:
            from publishing_engine.schemas import CaptionSpec, HashtagGroups, MediaRefs

            spec.metadata = CaptionSpec.model_validate(
                {k: meta.get(k) for k in ("body", "title", "mentions") if k in meta or k == "body"}
            )
            if "hashtags" in meta:
                spec.hashtags = HashtagGroups.model_validate(meta.get("hashtags") or {})
            if "media" in meta:
                spec.media = MediaRefs.model_validate(meta["media"])
            elif plan.master_artifact_id or meta.get("storage_uri"):
                spec.media = MediaRefs(
                    master_artifact_id=plan.master_artifact_id,
                    cover_artifact_id=plan.cover_artifact_id,
                    storage_uri=meta.get("storage_uri"),
                    cover_storage_uri=meta.get("cover_storage_uri"),
                    duration_sec=meta.get("duration_sec"),
                    width=meta.get("width"),
                    height=meta.get("height"),
                    mime_type=meta.get("mime_type"),
                )

        try:
            assert_qa_gate(spec)
        except PublishBlockedError as exc:
            if plan.status in {"draft", "approved", "scheduled", "queued", "failed"}:
                plan.status = transition_plan(plan.status, "blocked")
            plan.lineage = {
                **(plan.lineage or {}),
                "block": {"reason": exc.reason, "details": exc.details},
            }
            self.session.flush()
            get_bus().publish(
                EventType.PUBLISHING_BLOCKED,
                {"plan_id": plan.id, "reason": exc.reason, "details": exc.details},
                producer="publishing-engine",
            )
            raise

        if plan.status == "draft":
            plan.status = transition_plan("draft", "approved")
        if plan.status in {"approved", "scheduled", "failed"}:
            plan.status = transition_plan(plan.status, "queued")
        if plan.status in {"queued", "partial"}:
            plan.status = transition_plan(plan.status, "publishing")
        elif plan.status != "publishing":
            raise PublishBlockedError("INVALID_PLAN_STATE", plan.status)

        get_bus().publish(
            EventType.PUBLISHING_QUEUED,
            {"plan_id": plan.id, "content_id": plan.content_id},
            producer="publishing-engine",
        )
        get_bus().publish(
            EventType.PUBLISHING_STARTED,
            {"plan_id": plan.id},
            producer="publishing-engine",
        )
        self.session.flush()

        from sqlalchemy import select

        jobs = list(
            self.session.scalars(
                select(PublishingJob).where(PublishingJob.publishing_plan_id == plan.id)
            ).all()
        )
        results = []
        for job in jobs:
            if job.status in {"published", "cancelled", "blocked"}:
                results.append(job.status)
                continue
            try:
                self.process_job(job.id, spec=spec, force=force)
                self.session.refresh(job)
                results.append(job.status)
            except Exception:  # noqa: BLE001
                self.session.refresh(job)
                results.append(job.status)

        published = sum(1 for s in results if s == "published")
        failed = sum(1 for s in results if s in {"failed", "blocked"})
        if published and not failed:
            plan.status = "completed"
        elif published and failed:
            plan.status = "partial"
        elif failed and not published:
            plan.status = "failed"
        plan.updated_at = datetime.now(timezone.utc)
        self.session.flush()

        if plan.status == "completed":
            get_bus().publish(
                EventType.PUBLISHING_COMPLETED,
                {"plan_id": plan.id, "published": published},
                producer="publishing-engine",
            )
        elif plan.status == "partial":
            get_bus().publish(
                EventType.PUBLISHING_COMPLETED,
                {"plan_id": plan.id, "published": published, "failed": failed, "partial": True},
                producer="publishing-engine",
            )
        elif plan.status == "failed":
            get_bus().publish(
                EventType.PUBLISHING_FAILED,
                {"plan_id": plan.id, "failed": failed},
                producer="publishing-engine",
            )
        return plan

    def process_job(
        self,
        job_id: str,
        *,
        spec: PublishingPlanSpec | None = None,
        force: bool = False,
    ) -> PublishingJob:
        job = self.session.get(PublishingJob, job_id)
        if not job:
            raise ValueError("publishing job not found")
        plan = self.session.get(PublishingPlan, job.publishing_plan_id)
        if not plan:
            raise ValueError("plan missing")

        if spec is None:
            meta = plan.metadata_json or {}
            from publishing_engine.schemas import (
                CaptionSpec,
                HashtagGroups,
                MediaRefs,
                PlatformTarget,
                PublishingPolicy,
                ScheduleSpec,
                ApprovalGate,
            )

            spec = PublishingPlanSpec(
                content_id=plan.content_id,
                approval=ApprovalGate.model_validate(plan.approval or {}),
                platforms=[PlatformTarget.model_validate(p) for p in (plan.platforms or [])],
                schedule=ScheduleSpec.model_validate(plan.schedule or {}),
                metadata=CaptionSpec.model_validate(
                    {k: meta.get(k) for k in ("body", "title", "mentions")}
                ),
                hashtags=HashtagGroups.model_validate(meta.get("hashtags") or {}),
                media=MediaRefs.model_validate(
                    meta.get("media")
                    or {
                        "master_artifact_id": plan.master_artifact_id,
                        "cover_artifact_id": plan.cover_artifact_id,
                        "storage_uri": meta.get("storage_uri"),
                        "cover_storage_uri": meta.get("cover_storage_uri"),
                        "duration_sec": meta.get("duration_sec"),
                        "width": meta.get("width"),
                        "height": meta.get("height"),
                    }
                ),
                policy=PublishingPolicy.model_validate(plan.policy or {}),
                assembly_id=plan.assembly_id,
                lineage=plan.lineage or {},
                force_republish=force,
            )

        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.attempt = int(job.attempt or 0) + 1
        self.session.flush()

        try:
            return self._execute_job(job, plan, spec, force=force)
        except PublishBlockedError as exc:
            job.status = "blocked"
            job.error = {"reason": exc.reason, "details": exc.details, "type": "blocked"}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.PUBLISHING_BLOCKED,
                {"job_id": job.id, "reason": exc.reason, "details": exc.details},
                producer="publishing-engine",
            )
            return job
        except PermanentPublishError as exc:
            job.status = "failed"
            job.error = {"message": str(exc), "retryable": False, "type": "permanent"}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.PUBLISHING_FAILED,
                {"job_id": job.id, "error": job.error},
                producer="publishing-engine",
            )
            return job
        except TransientPublishError as exc:
            if job.attempt < MAX_ATTEMPTS:
                job.status = transition_job(job.status if job.status != "failed" else "failed", "retry")
                job.error = {"message": str(exc), "retryable": True, "type": "transient"}
                self.session.flush()
                get_bus().publish(
                    EventType.PUBLISHING_RETRY,
                    {"job_id": job.id, "attempt": job.attempt},
                    producer="publishing-engine",
                )
                job.status = transition_job("retry", "validating")
                return self._execute_job(job, plan, spec, force=force)
            job.status = "failed"
            job.error = {"message": str(exc), "retryable": True, "exhausted": True}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.PUBLISHING_FAILED,
                {"job_id": job.id, "error": job.error},
                producer="publishing-engine",
            )
            return job
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = {"message": str(exc), "type": type(exc).__name__}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.PUBLISHING_FAILED,
                {"job_id": job.id, "error": job.error},
                producer="publishing-engine",
            )
            return job

    def _execute_job(
        self,
        job: PublishingJob,
        plan: PublishingPlan,
        spec: PublishingPlanSpec,
        *,
        force: bool,
    ) -> PublishingJob:
        provider = get_provider(job.platform)

        job.status = transition_job(
            job.status if job.status in JOB_STARTABLE else "queued", "validating"
        )
        self.session.flush()

        assert_qa_gate(spec)
        assert_platform_allowed(spec, job.platform)
        account = assert_account_ready(self.session, job.social_account_id, job.platform)
        assert_not_duplicate(
            self.session,
            content_id=plan.content_id,
            account_id=account.id,
            platform=job.platform,
            force=force or spec.force_republish,
        )
        assert_rate_limit(self.session, account.id, job.platform)

        # Token refresh if needed
        self._ensure_token(account.id, provider)

        package = build_platform_package(
            spec, job.platform, account.id, session=self.session
        )
        media_issues = validate_media_against_profile(package)
        provider_issues = provider.validate_post(package.model_dump())
        issues = media_issues + provider_issues
        if issues:
            raise PublishBlockedError("INVALID_MEDIA", "; ".join(issues))

        job.platform_package = package.model_dump()
        self.session.flush()

        idem = job.idempotency_key or f"{plan.id}:{job.platform}:{account.id}"
        job.idempotency_key = idem

        # Reuse prior upload if present
        media_id = job.external_media_id
        if not media_id:
            job.status = transition_job(job.status, "uploading")
            self.session.flush()
            get_bus().publish(
                EventType.MEDIA_UPLOAD_STARTED,
                {"job_id": job.id, "platform": job.platform},
                producer="publishing-engine",
            )
            upload = provider.upload_media(package.model_dump(), idempotency_key=idem)
            media_id = upload["external_media_id"]
            job.external_media_id = media_id
            get_bus().publish(
                EventType.MEDIA_UPLOAD_COMPLETED,
                {"job_id": job.id, "external_media_id": media_id},
                producer="publishing-engine",
            )
            job.status = transition_job(job.status, "processing")
            self.session.flush()
        else:
            if job.status == "validating":
                job.status = transition_job("validating", "uploading")
                job.status = transition_job("uploading", "processing")

        job.status = transition_job(job.status, "publishing")
        self.session.flush()
        get_bus().publish(
            EventType.PUBLISHING_STARTED,
            {"job_id": job.id, "platform": job.platform},
            producer="publishing-engine",
        )

        published = provider.publish(
            package.model_dump(),
            external_media_id=media_id,
            idempotency_key=idem,
        )
        job.status = transition_job(job.status, "verifying")
        self.session.flush()

        verified = provider.get_post(published["external_post_id"])
        if not verified.get("exists") and verified.get("status") != "published":
            raise TransientPublishError("post not visible yet")

        url = published.get("url") or provider.get_post_url(published["external_post_id"])
        now = datetime.now(timezone.utc)
        receipt = PublicationReceipt(
            id=str(uuid4()),
            publishing_job_id=job.id,
            publishing_plan_id=plan.id,
            content_id=plan.content_id,
            platform=job.platform,
            social_account_id=account.id,
            external_post_id=published["external_post_id"],
            external_media_id=media_id,
            post_url=url,
            published_at=now,
            verification_status="verified",
            verified_at=now,
            raw_response={"publish": published, "verify": verified},
            lineage={
                **(plan.lineage or {}),
                "assembly_id": plan.assembly_id,
                "content_id": plan.content_id,
                "plan_id": plan.id,
                "job_id": job.id,
                "prediction_id": (plan.lineage or {}).get("prediction_id"),
            },
        )
        self.session.add(receipt)
        job.status = transition_job(job.status, "published")
        job.completed_at = now
        job.error = None
        self.session.flush()

        get_bus().publish(
            EventType.PUBLISHING_COMPLETED,
            {
                "job_id": job.id,
                "platform": job.platform,
                "external_post_id": receipt.external_post_id,
                "url": receipt.post_url,
            },
            producer="publishing-engine",
        )
        get_bus().publish(
            EventType.PUBLICATION_VERIFIED,
            {
                "receipt_id": receipt.id,
                "platform": job.platform,
                "external_post_id": receipt.external_post_id,
                "url": receipt.post_url,
                "content_id": plan.content_id,
                "prediction_id": (plan.lineage or {}).get("prediction_id"),
            },
            producer="publishing-engine",
        )
        # Close the loop: start Performance Engine tracking (non-fatal)
        try:
            from performance_engine.service import PerformanceService

            PerformanceService(self.session).start_tracking(
                {
                    "publication_id": receipt.id,
                    "prediction": {
                        "prediction_id": (plan.lineage or {}).get("prediction_id"),
                    },
                    "content_fingerprint": {
                        "character": (plan.lineage or {}).get("character_slug"),
                    },
                    "collect_now": True,
                    "simulate_age_sec": 300,
                    "growth_profile": "normal",
                }
            )
        except Exception:  # noqa: BLE001
            pass
        return job

    def _ensure_token(self, account_id: str, provider: Any) -> None:
        from sqlalchemy import select
        from db.models import SocialAccount

        account = self.session.get(SocialAccount, account_id)
        cred = self.session.scalar(
            select(SocialCredential)
            .where(SocialCredential.social_account_id == account_id)
            .where(SocialCredential.status == "active")
            .order_by(SocialCredential.created_at.desc())
        )
        if not cred:
            raise PublishBlockedError("CREDENTIAL_MISSING", account_id)
        payload = load_secret(cred.credential_reference)
        if account and account.token_status == "refresh_required":
            refreshed = provider.refresh_token(payload)
            new_ref = store_secret(refreshed)
            cred.credential_reference = new_ref
            cred.last_refreshed_at = datetime.now(timezone.utc)
            cred.refresh_status = "ok"
            account.token_status = "active"
            self.session.flush()


JOB_STARTABLE = {
    "draft",
    "approved",
    "scheduled",
    "queued",
    "validating",
    "failed",
    "retry",
    "uploading",
    "processing",
    "publishing",
}
