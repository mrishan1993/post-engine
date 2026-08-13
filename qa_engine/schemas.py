from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


QaDecision = Literal["pass", "repair", "regenerate", "block", "review_required"]
Severity = Literal["critical", "high", "medium", "low", "info"]
RecommendedAction = Literal["none", "repair", "regenerate", "block", "review"]


class QaIssueSpec(BaseModel):
    code: str
    severity: Severity = "medium"
    category: str | None = None
    artifact_id: str | None = None
    scene_id: str | None = None
    timestamp_sec: float | None = None
    score: float | None = None
    message: str = ""
    owner_engine: str | None = None
    recommended_action: RecommendedAction = "none"
    metadata: dict[str, Any] = Field(default_factory=dict)


class QaMeasurementSpec(BaseModel):
    dimension: str
    metric: str
    value: float | None = None
    threshold: float | None = None
    passed: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class DimensionResult(BaseModel):
    dimension: str
    score: float
    passed: bool = True
    issues: list[QaIssueSpec] = Field(default_factory=list)
    measurements: list[QaMeasurementSpec] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    skipped: bool = False


class QaThresholds(BaseModel):
    pass_score: float = 0.85
    repair_score: float = 0.70
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "technical": 0.15,
            "visual": 0.15,
            "audio": 0.10,
            "character": 0.15,
            "story": 0.15,
            "storyboard": 0.10,
            "captions": 0.05,
            "platform": 0.05,
            "safety": 0.05,
            "predicted_quality": 0.05,
        }
    )
    # Safety is a hard gate — these map policy_risk
    safety_block_levels: list[str] = Field(default_factory=lambda: ["high"])
    safety_review_levels: list[str] = Field(default_factory=lambda: ["medium"])
    character_min_score: float = 0.70
    technical_min_score: float = 0.80
    caption_timing_tolerance_ms: float = 120.0


class QaPackage(BaseModel):
    """Inputs for a QA run — resolved from assembly + upstream lineage."""

    content_id: str
    assembly_id: str | None = None
    artifact_id: str | None = None
    storage_uri: str | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    platform_profile: str = "instagram_reels_v1"
    target_platforms: list[str] = Field(default_factory=lambda: ["instagram", "youtube"])
    # Assembly / timeline context
    specification: dict[str, Any] = Field(default_factory=dict)
    timeline: dict[str, Any] = Field(default_factory=dict)
    technical_qa: dict[str, Any] = Field(default_factory=dict)
    # Upstream creative context
    story: dict[str, Any] = Field(default_factory=dict)
    storyboard: dict[str, Any] = Field(default_factory=dict)
    character_slug: str | None = None
    character_canon: dict[str, Any] = Field(default_factory=dict)
    expected_script: str | None = None
    captions: list[dict[str, Any]] = Field(default_factory=list)
    overlays: list[dict[str, Any]] = Field(default_factory=list)
    voice_clips: list[dict[str, Any]] = Field(default_factory=list)
    music_clips: list[dict[str, Any]] = Field(default_factory=list)
    sfx_clips: list[dict[str, Any]] = Field(default_factory=list)
    # Provenance / prediction
    asset_provenance: dict[str, Any] = Field(default_factory=dict)
    prediction: dict[str, Any] = Field(default_factory=dict)
    # Injected overrides for tests / forced outcomes
    injected_issues: list[QaIssueSpec] = Field(default_factory=list)
    force_safety_risk: Literal["none", "low", "medium", "high"] | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)


class QaResult(BaseModel):
    content_id: str
    decision: QaDecision
    overall_score: float
    dimensions: dict[str, float] = Field(default_factory=dict)
    issues: list[QaIssueSpec] = Field(default_factory=list)
    measurements: list[QaMeasurementSpec] = Field(default_factory=list)
    policy_risk: Literal["none", "low", "medium", "high"] = "none"
    repair_actions: list[dict[str, Any]] = Field(default_factory=list)
    regeneration_targets: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)


class CreateQaRunRequest(BaseModel):
    content_id: str | None = None
    assembly_id: str | None = None
    artifact_id: str | None = None
    storage_uri: str | None = None
    package: QaPackage | dict[str, Any] | None = None
    thresholds: QaThresholds | dict[str, Any] | None = None
    target_platforms: list[str] = Field(default_factory=lambda: ["instagram", "youtube"])
    process: bool = True
    # Optional creative context shortcuts
    character_slug: str | None = None
    prediction: dict[str, Any] = Field(default_factory=dict)
    force_safety_risk: Literal["none", "low", "medium", "high"] | None = None
    injected_issues: list[QaIssueSpec] = Field(default_factory=list)


class HumanReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "regenerate", "edit"]
    reviewer: str = "human"
    reasons: list[str] = Field(default_factory=list)
    notes: str | None = None
