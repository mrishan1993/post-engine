from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal[
    "queued",
    "validating",
    "routing",
    "submitted",
    "processing",
    "completed",
    "qa_pending",
    "approved",
    "failed",
    "retry",
    "fallback",
    "failed_permanently",
    "cancelled",
]

Priority = Literal["critical", "high", "normal", "low"]
StrategyMode = Literal["automatic", "preferred", "locked"]


class ProviderStrategy(BaseModel):
    mode: StrategyMode = "automatic"
    preferred: str | None = None
    locked: str | None = None
    fallback: list[str] = Field(default_factory=list)
    max_provider_switches: int = 2


class BudgetConfig(BaseModel):
    max_cost: float = 5.0
    currency: str = "USD"
    max_variants: int | None = None


class QualityConfig(BaseModel):
    minimum_score: float = 0.0


class VariantsConfig(BaseModel):
    count: int = 1
    strategy: Literal[
        "same_provider_seed",
        "mixed_providers",
        "same_provider",
    ] = "same_provider_seed"


class GenerationRequestIn(BaseModel):
    prompt_package_id: str | None = None
    storyboard_id: str | None = None
    storyboard_shot_id: str | None = None
    content_id: str | None = None
    modality: str | None = None
    provider_strategy: ProviderStrategy = Field(default_factory=ProviderStrategy)
    variants: VariantsConfig = Field(default_factory=VariantsConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    priority: Priority = "normal"
    profile: str | None = None
    idempotency_key: str | None = None
    process: bool = True  # Phase-0: execute immediately after queue
    depends_on_job_ids: list[str] = Field(default_factory=list)


class GenerationEstimate(BaseModel):
    provider: str
    estimated_cost: float
    estimated_latency_sec: float
    confidence: float = 0.85


class TechnicalQAResult(BaseModel):
    ok: bool
    file_exists: bool = False
    readable: bool = False
    duration_valid: bool = True
    resolution_valid: bool = True
    size_bytes: int = 0
    notes: list[str] = Field(default_factory=list)


GENERATION_PROFILES: dict[str, dict[str, Any]] = {
    "fast_social": {
        "quality": "balanced",
        "provider_strategy": {"mode": "automatic"},
        "max_cost_per_scene": 0.50,
        "variants": 2,
        "fallback_enabled": True,
        "priority": "normal",
    },
    "maximum_quality": {
        "quality": "high",
        "provider_strategy": {"mode": "automatic"},
        "max_cost_per_scene": 2.0,
        "variants": 3,
        "fallback_enabled": True,
        "priority": "high",
    },
    "lowest_cost": {
        "quality": "balanced",
        "provider_strategy": {"mode": "automatic"},
        "max_cost_per_scene": 0.25,
        "variants": 1,
        "fallback_enabled": True,
        "priority": "low",
    },
    "experimental": {
        "quality": "balanced",
        "provider_strategy": {"mode": "automatic"},
        "max_cost_per_scene": 1.0,
        "variants": 4,
        "fallback_enabled": True,
        "priority": "low",
    },
}
