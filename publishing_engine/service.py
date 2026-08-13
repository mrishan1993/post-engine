from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from publishing_engine.credentials import delete_secret, store_secret
from publishing_engine.executor import PublishingExecutor
from publishing_engine.package_builder import build_platform_package
from publishing_engine.profiles import get_platform_profile
from publishing_engine.providers.stub import PublishBlockedError
from publishing_engine.registry import get_provider
from publishing_engine.schemas import (
    ConnectAccountRequest,
    CreatePlanRequest,
    PublicationReceiptOut,
    PublishPlanRequest,
    PublishingPlanSpec,
    SchedulePlanRequest,
)
from publishing_engine.state import transition_job, transition_plan
from publishing_engine.validation import assert_qa_gate, approval_dict
from db.models import (
    PublicationReceipt,
    PublishingJob,
    PublishingPlan,
    SocialAccount,
    SocialCredential,
)


class PublishingService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ accounts
    def connect_account(self, request: ConnectAccountRequest | dict[str, Any]) -> SocialAccount:
        req = (
            request
            if isinstance(request, ConnectAccountRequest)
            else ConnectAccountRequest.model_validate(request)
        )
        provider = get_provider(req.platform)
        auth = provider.authenticate(
            {
                "access_token": req.access_token,
                "refresh_token": req.refresh_token,
                "external_account_id": req.external_account_id,
                "scopes": req.scopes,
            }
        )
        profile = get_platform_profile(req.platform)
        existing = self.session.scalar(
            select(SocialAccount).where(
                SocialAccount.platform == req.platform,
                SocialAccount.external_account_id == req.external_account_id,
            )
        )
        if existing:
            account = existing
            account.status = "connected"
            account.token_status = "active"
            account.display_name = req.display_name or account.display_name
            account.username = req.username or account.username
            account.timezone = req.timezone
            account.character_slug = req.character_slug or account.character_slug
            account.permissions = list(req.scopes)
            account.capabilities = profile.get("capabilities")
            account.updated_at = datetime.now(timezone.utc)
        else:
            account = SocialAccount(
                id=str(uuid4()),
                platform=req.platform,
                external_account_id=req.external_account_id,
                display_name=req.display_name or req.username,
                username=req.username,
                timezone=req.timezone,
                status="connected",
                token_status="active",
                permissions=list(req.scopes),
                capabilities=profile.get("capabilities"),
                character_slug=req.character_slug,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(account)
            self.session.flush()

        ref = store_secret(
            {
                "access_token": req.access_token,
                "refresh_token": req.refresh_token,
                "external_account_id": req.external_account_id,
                "platform": req.platform,
                "scopes": req.scopes,
                "stub_oauth": req.stub_oauth,
                "auth": auth,
            }
        )
        # Deactivate prior credentials
        for old in self.session.scalars(
            select(SocialCredential).where(SocialCredential.social_account_id == account.id)
        ).all():
            old.status = "revoked"
        cred = SocialCredential(
            id=str(uuid4()),
            social_account_id=account.id,
            credential_reference=ref,
            expires_at=req.expires_at,
            scopes=list(req.scopes),
            status="active",
            last_refreshed_at=datetime.now(timezone.utc),
            refresh_status="ok",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(cred)
        self.session.flush()

        get_bus().publish(
            EventType.SOCIAL_ACCOUNT_CONNECTED,
            {
                "account_id": account.id,
                "platform": account.platform,
                "username": account.username,
                "external_account_id": account.external_account_id,
            },
            producer="publishing-engine",
        )
        return account

    def list_accounts(self, platform: str | None = None) -> list[SocialAccount]:
        stmt = select(SocialAccount).order_by(SocialAccount.created_at.desc())
        if platform:
            stmt = stmt.where(SocialAccount.platform == platform)
        return list(self.session.scalars(stmt).all())

    def disconnect_account(self, account_id: str) -> SocialAccount:
        account = self._get_account(account_id)
        account.status = "disconnected"
        account.token_status = "revoked"
        account.updated_at = datetime.now(timezone.utc)
        for cred in self.session.scalars(
            select(SocialCredential).where(SocialCredential.social_account_id == account.id)
        ).all():
            delete_secret(cred.credential_reference)
            cred.status = "revoked"
            cred.credential_reference = "secret://revoked"
        self.session.flush()
        get_bus().publish(
            EventType.SOCIAL_ACCOUNT_DISCONNECTED,
            {"account_id": account.id, "platform": account.platform},
            producer="publishing-engine",
        )
        return account

    # ------------------------------------------------------------------ plans
    def create_plan(self, request: CreatePlanRequest | dict[str, Any]) -> PublishingPlan:
        req = (
            request
            if isinstance(request, CreatePlanRequest)
            else CreatePlanRequest.model_validate(request)
        )
        plan_spec = req.plan
        if plan_spec.idempotency_key:
            existing = self.session.scalar(
                select(PublishingPlan).where(
                    PublishingPlan.idempotency_key == plan_spec.idempotency_key
                )
            )
            if existing:
                return existing

        meta = {
            "body": plan_spec.metadata.body,
            "title": plan_spec.metadata.title,
            "mentions": plan_spec.metadata.mentions,
            "hashtags": plan_spec.hashtags.model_dump(),
            "media": plan_spec.media.model_dump(),
            "storage_uri": plan_spec.media.storage_uri,
            "cover_storage_uri": plan_spec.media.cover_storage_uri,
            "duration_sec": plan_spec.media.duration_sec,
            "width": plan_spec.media.width,
            "height": plan_spec.media.height,
            "mime_type": plan_spec.media.mime_type,
        }
        lineage = {
            **plan_spec.lineage,
            "prediction_id": plan_spec.prediction_id,
            "story_id": plan_spec.story_id,
            "storyboard_id": plan_spec.storyboard_id,
            "character_slug": plan_spec.character_slug,
            "assembly_id": plan_spec.assembly_id,
        }
        plan = PublishingPlan(
            id=str(uuid4()),
            content_id=plan_spec.content_id,
            assembly_id=plan_spec.assembly_id,
            master_artifact_id=plan_spec.media.master_artifact_id,
            cover_artifact_id=plan_spec.media.cover_artifact_id,
            status="draft",
            schedule=plan_spec.schedule.model_dump(mode="json"),
            metadata_json=meta,
            approval=approval_dict(plan_spec.approval),
            policy=plan_spec.policy.model_dump(),
            platforms=[p.model_dump() for p in plan_spec.platforms],
            lineage=lineage,
            idempotency_key=plan_spec.idempotency_key,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(plan)
        self.session.flush()

        for target in plan_spec.platforms:
            pkg = None
            try:
                pkg = build_platform_package(
                    plan_spec, target.platform, target.account_id, session=self.session
                ).model_dump()
            except Exception:  # noqa: BLE001
                pkg = {"platform": target.platform, "account_id": target.account_id}
            job = PublishingJob(
                id=str(uuid4()),
                publishing_plan_id=plan.id,
                platform=target.platform,
                social_account_id=target.account_id,
                platform_package=pkg,
                status="queued",
                scheduled_at=(
                    plan_spec.schedule.publish_at
                    if plan_spec.schedule.mode == "scheduled"
                    else None
                ),
                attempt=0,
                idempotency_key=f"{plan.id}:{target.platform}:{target.account_id}",
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(job)
        self.session.flush()

        get_bus().publish(
            EventType.PUBLISHING_PLAN_CREATED,
            {
                "plan_id": plan.id,
                "content_id": plan.content_id,
                "platforms": [p.platform for p in plan_spec.platforms],
            },
            producer="publishing-engine",
        )

        # Auto-approve path when QA already passed + policy auto
        if (
            plan_spec.approval.approved
            and plan_spec.approval.qa_status == "passed"
            and (plan_spec.policy.mode == "auto" or plan_spec.policy.auto_publish)
        ):
            self.approve_plan(plan.id, reviewer=plan_spec.approval.reviewer or "auto")
            if req.process:
                return self.publish_plan(PublishPlanRequest(plan_id=plan.id, process=True))
        elif req.process and plan_spec.approval.approved and plan_spec.approval.qa_status == "passed":
            self.approve_plan(plan.id, reviewer=plan_spec.approval.reviewer or "system")
            return self.publish_plan(PublishPlanRequest(plan_id=plan.id, process=True))

        return plan

    def approve_plan(self, plan_id: str, *, reviewer: str = "human") -> PublishingPlan:
        plan = self._get_plan(plan_id)
        approval = dict(plan.approval or {})
        if approval.get("qa_status") != "passed":
            raise PublishBlockedError("QA_REQUIRED", "cannot approve without QA pass")
        if approval.get("policy_risk") == "high":
            raise PublishBlockedError("POLICY_RISK", "high policy risk")
        approval["approved"] = True
        approval["reviewer"] = reviewer
        approval["approved_at"] = datetime.now(timezone.utc).isoformat()
        plan.approval = approval
        if plan.status == "draft":
            plan.status = transition_plan("draft", "approved")
        plan.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        get_bus().publish(
            EventType.PUBLISHING_PLAN_APPROVED,
            {"plan_id": plan.id, "reviewer": reviewer},
            producer="publishing-engine",
        )
        return plan

    def schedule_plan(self, request: SchedulePlanRequest | dict[str, Any]) -> PublishingPlan:
        req = (
            request
            if isinstance(request, SchedulePlanRequest)
            else SchedulePlanRequest.model_validate(request)
        )
        plan = self._get_plan(req.plan_id)
        if plan.status == "draft":
            self.approve_plan(plan.id)
            self.session.refresh(plan)
        plan.schedule = {
            "mode": "scheduled",
            "publish_at": req.publish_at.isoformat(),
            "timezone": req.timezone,
        }
        if plan.status in {"approved", "failed"}:
            plan.status = transition_plan(plan.status, "scheduled")
        elif plan.status == "draft":
            plan.status = transition_plan("draft", "approved")
            plan.status = transition_plan("approved", "scheduled")
        for job in self.list_jobs(plan.id):
            if job.status in {"queued", "approved", "draft", "scheduled"}:
                job.status = "scheduled"
                job.scheduled_at = req.publish_at
        plan.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        get_bus().publish(
            EventType.PUBLISHING_SCHEDULED,
            {
                "plan_id": plan.id,
                "publish_at": req.publish_at.isoformat(),
                "timezone": req.timezone,
            },
            producer="publishing-engine",
        )
        if req.process_when_due:
            return self.publish_plan(PublishPlanRequest(plan_id=plan.id, process=True))
        return plan

    def publish_plan(self, request: PublishPlanRequest | dict[str, Any]) -> PublishingPlan:
        req = (
            request
            if isinstance(request, PublishPlanRequest)
            else PublishPlanRequest.model_validate(request)
        )
        plan = self._get_plan(req.plan_id)
        # Ensure approval recorded
        approval = plan.approval or {}
        if not approval.get("approved"):
            raise PublishBlockedError("APPROVAL_REQUIRED", "approve plan before publish")
        if req.process:
            return PublishingExecutor(self.session).process_plan(plan.id, force=req.force)
        if plan.status == "approved":
            plan.status = transition_plan("approved", "queued")
        self.session.flush()
        return plan

    def retry_job(self, job_id: str) -> PublishingJob:
        job = self._get_job(job_id)
        if job.status not in {"failed", "blocked"}:
            raise ValueError(f"cannot retry job in status {job.status}")
        if job.status == "blocked":
            raise PublishBlockedError("BLOCKED", "blocked jobs need remediation, not retry")
        job.status = transition_job("failed", "retry")
        job.status = transition_job("retry", "queued")
        job.error = None
        self.session.flush()
        return PublishingExecutor(self.session).process_job(job.id)

    def cancel_job(self, job_id: str) -> PublishingJob:
        job = self._get_job(job_id)
        if job.status in {"published", "cancelled"}:
            return job
        if job.status in {"queued", "scheduled", "approved", "draft", "validating"}:
            job.status = "cancelled"
        else:
            job.status = transition_job(job.status, "cancelled") if False else "cancelled"
        self.session.flush()
        return job

    def verify_job(self, job_id: str) -> PublicationReceipt:
        job = self._get_job(job_id)
        receipt = self.session.scalar(
            select(PublicationReceipt).where(PublicationReceipt.publishing_job_id == job.id)
        )
        if not receipt or not receipt.external_post_id:
            raise ValueError("no receipt to verify")
        provider = get_provider(job.platform)
        verified = provider.get_post(receipt.external_post_id)
        receipt.verification_status = "verified" if verified.get("exists") else "failed"
        receipt.verified_at = datetime.now(timezone.utc)
        receipt.raw_response = {**(receipt.raw_response or {}), "reverify": verified}
        self.session.flush()
        get_bus().publish(
            EventType.PUBLICATION_VERIFIED,
            {
                "receipt_id": receipt.id,
                "platform": job.platform,
                "external_post_id": receipt.external_post_id,
                "status": receipt.verification_status,
            },
            producer="publishing-engine",
        )
        return receipt

    def get_plan(self, plan_id: str) -> PublishingPlan | None:
        try:
            return self._get_plan(plan_id)
        except ValueError:
            return None

    def list_jobs(self, plan_id: str) -> list[PublishingJob]:
        return list(
            self.session.scalars(
                select(PublishingJob).where(PublishingJob.publishing_plan_id == plan_id)
            ).all()
        )

    def get_receipt(self, job_id: str) -> PublicationReceiptOut | None:
        job = self._get_job(job_id)
        receipt = self.session.scalar(
            select(PublicationReceipt).where(PublicationReceipt.publishing_job_id == job.id)
        )
        if not receipt:
            return None
        return PublicationReceiptOut(
            publication_id=receipt.id,
            platform=receipt.platform,
            account_id=receipt.social_account_id,
            status=job.status,
            external_post_id=receipt.external_post_id,
            external_media_id=receipt.external_media_id,
            url=receipt.post_url,
            published_at=receipt.published_at,
            verification_status=receipt.verification_status,
            content_id=receipt.content_id,
        )

    def list_receipts(self, plan_id: str) -> list[PublicationReceipt]:
        return list(
            self.session.scalars(
                select(PublicationReceipt).where(PublicationReceipt.publishing_plan_id == plan_id)
            ).all()
        )

    def _get_plan(self, plan_id: str) -> PublishingPlan:
        row = self.session.get(PublishingPlan, plan_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(PublishingPlan).where(PublishingPlan.id.startswith(plan_id))
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("publishing plan not found")
        return rows[0]

    def _get_job(self, job_id: str) -> PublishingJob:
        row = self.session.get(PublishingJob, job_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(PublishingJob).where(PublishingJob.id.startswith(job_id))
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("publishing job not found")
        return rows[0]

    def _get_account(self, account_id: str) -> SocialAccount:
        row = self.session.get(SocialAccount, account_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(SocialAccount).where(SocialAccount.id.startswith(account_id))
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("social account not found")
        return rows[0]
