from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from publishing_engine.profiles import get_platform_profile
from publishing_engine.providers.stub import PublishBlockedError
from publishing_engine.schemas import ApprovalGate, PublishingPlanSpec, PublishingPolicy
from db.models import PublicationReceipt, PublishingJob, SocialAccount, SocialCredential


def assert_qa_gate(plan: PublishingPlanSpec, policy: PublishingPolicy | None = None) -> None:
    pol = policy or plan.policy
    approval = plan.approval
    if pol.require_qa and approval.qa_status != "passed":
        raise PublishBlockedError("QA_REQUIRED", f"qa_status={approval.qa_status}")
    if approval.qa_status == "failed":
        raise PublishBlockedError("QA_FAILED", approval.notes or "QA did not pass")
    if approval.policy_risk in (pol.block_on_policy_risk or []):
        raise PublishBlockedError("POLICY_RISK", f"policy_risk={approval.policy_risk}")
    if pol.require_human_approval or pol.mode == "approval_required":
        if not approval.approved:
            raise PublishBlockedError("APPROVAL_REQUIRED", "human/policy approval missing")
    if not approval.approved and pol.mode != "auto":
        raise PublishBlockedError("APPROVAL_REQUIRED", "plan not approved")


def assert_account_ready(session: Session, account_id: str, platform: str) -> SocialAccount:
    account = session.get(SocialAccount, account_id)
    if not account:
        raise PublishBlockedError("ACCOUNT_MISSING", account_id)
    if account.platform != platform:
        raise PublishBlockedError("ACCOUNT_PLATFORM_MISMATCH", f"{account.platform}!={platform}")
    if account.status != "connected":
        raise PublishBlockedError("ACCOUNT_DISCONNECTED", account.status)
    if account.token_status not in {"active", "refreshed"}:
        raise PublishBlockedError("TOKEN_INVALID", account.token_status)
    cred = session.scalar(
        select(SocialCredential)
        .where(SocialCredential.social_account_id == account.id)
        .where(SocialCredential.status == "active")
        .order_by(SocialCredential.created_at.desc())
    )
    if not cred:
        raise PublishBlockedError("CREDENTIAL_MISSING", account_id)
    if cred.expires_at and cred.expires_at < datetime.now(timezone.utc):
        raise PublishBlockedError("TOKEN_EXPIRED", str(cred.expires_at))
    return account


def assert_not_duplicate(
    session: Session,
    *,
    content_id: str,
    account_id: str,
    platform: str,
    force: bool = False,
) -> None:
    if force:
        return
    rows = list(
        session.scalars(
            select(PublicationReceipt).where(
                PublicationReceipt.content_id == content_id,
                PublicationReceipt.platform == platform,
                PublicationReceipt.social_account_id == account_id,
                PublicationReceipt.verification_status == "verified",
            )
        ).all()
    )
    if rows:
        raise PublishBlockedError(
            "DUPLICATE_PUBLISH_BLOCKED",
            f"content={content_id} platform={platform} account={account_id}",
        )


def assert_platform_allowed(plan: PublishingPlanSpec, platform: str) -> None:
    allowed = plan.policy.allowed_platforms or []
    if allowed and platform not in allowed:
        raise PublishBlockedError("PLATFORM_NOT_ALLOWED", platform)


def assert_rate_limit(session: Session, account_id: str, platform: str) -> None:
    profile = get_platform_profile(platform)
    max_day = int((profile.get("rate_limit") or {}).get("posts_per_day") or 100)
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    jobs = list(
        session.scalars(
            select(PublishingJob).where(
                PublishingJob.social_account_id == account_id,
                PublishingJob.platform == platform,
                PublishingJob.status == "published",
                PublishingJob.completed_at >= since,
            )
        ).all()
    )
    if len(jobs) >= max_day:
        raise PublishBlockedError("RATE_LIMIT", f"{len(jobs)}>={max_day}")


def approval_dict(approval: ApprovalGate) -> dict[str, Any]:
    return approval.model_dump(mode="json")
