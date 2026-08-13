from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PlatformId = Literal["instagram", "youtube", "tiktok"]
ScheduleMode = Literal["immediate", "scheduled", "optimal"]
PublishPolicyMode = Literal["auto", "approval_required", "manual"]


class ApprovalGate(BaseModel):
    qa_status: Literal["passed", "failed", "pending", "skipped"] = "pending"
    approved: bool = False
    policy_risk: Literal["none", "low", "medium", "high"] = "none"
    reviewer: str | None = None
    notes: str | None = None
    approved_at: datetime | None = None


class ScheduleSpec(BaseModel):
    mode: ScheduleMode = "immediate"
    publish_at: datetime | None = None  # UTC
    timezone: str = "UTC"


class HashtagGroups(BaseModel):
    broad: list[str] = Field(default_factory=list)
    niche: list[str] = Field(default_factory=list)
    trend: list[str] = Field(default_factory=list)

    def flattened(self) -> list[str]:
        out: list[str] = []
        for group in (self.broad, self.niche, self.trend):
            for tag in group:
                t = tag.strip()
                if not t:
                    continue
                if not t.startswith("#"):
                    t = f"#{t}"
                if t not in out:
                    out.append(t)
        return out


class CaptionSpec(BaseModel):
    body: str = ""
    title: str | None = None
    mentions: list[str] = Field(default_factory=list)


class PlatformTarget(BaseModel):
    platform: PlatformId
    account_id: str
    # Optional per-platform metadata override (from Strategy/Prompt — not invented here)
    title: str | None = None
    caption: str | None = None
    hashtags: list[str] | HashtagGroups | None = None
    artifact_id: str | None = None  # platform-specific render derivative


class MediaRefs(BaseModel):
    master_artifact_id: str | None = None
    cover_artifact_id: str | None = None
    storage_uri: str | None = None  # direct path when artifact row not used
    cover_storage_uri: str | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None


class PublishingPolicy(BaseModel):
    mode: PublishPolicyMode = "approval_required"
    auto_publish: bool = False
    require_qa: bool = True
    require_probability_threshold: float | None = None
    require_human_approval: bool = True
    allowed_platforms: list[PlatformId] = Field(
        default_factory=lambda: ["instagram", "youtube"]
    )
    max_posts_per_day: int = 5
    block_on_policy_risk: list[str] = Field(default_factory=lambda: ["high"])


class PlatformPostPackage(BaseModel):
    platform: PlatformId
    account_id: str
    media_uri: str
    cover_uri: str | None = None
    title: str | None = None
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    content_type: str = "reel"
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublishingPlanSpec(BaseModel):
    content_id: str
    approval: ApprovalGate = Field(default_factory=ApprovalGate)
    platforms: list[PlatformTarget]
    schedule: ScheduleSpec = Field(default_factory=ScheduleSpec)
    metadata: CaptionSpec = Field(default_factory=CaptionSpec)
    hashtags: HashtagGroups = Field(default_factory=HashtagGroups)
    media: MediaRefs = Field(default_factory=MediaRefs)
    policy: PublishingPolicy = Field(default_factory=PublishingPolicy)
    assembly_id: str | None = None
    prediction_id: str | None = None
    story_id: str | None = None
    storyboard_id: str | None = None
    character_slug: str | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    force_republish: bool = False


class ConnectAccountRequest(BaseModel):
    platform: PlatformId
    external_account_id: str
    display_name: str | None = None
    username: str | None = None
    timezone: str = "UTC"
    character_slug: str | None = None
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scopes: list[str] = Field(default_factory=lambda: ["publishing", "analytics"])
    # Stub OAuth: when True, accept without real OAuth dance
    stub_oauth: bool = True


class CreatePlanRequest(BaseModel):
    plan: PublishingPlanSpec
    process: bool = False  # approve+publish immediately if policy allows


class PublishPlanRequest(BaseModel):
    plan_id: str
    force: bool = False
    process: bool = True


class SchedulePlanRequest(BaseModel):
    plan_id: str
    publish_at: datetime
    timezone: str = "UTC"
    process_when_due: bool = False


class PublicationReceiptOut(BaseModel):
    publication_id: str
    platform: str
    account_id: str | None = None
    status: str
    external_post_id: str | None = None
    external_media_id: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    verification_status: str = "pending"
    content_id: str | None = None
