from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


VerificationStage = Literal["early", "intermediate", "primary", "long_term"]
VerificationStatus = Literal[
    "pending", "early_result", "verified", "insufficient_data", "invalid"
]


class PredictionTarget(BaseModel):
    metric: str = "views"
    threshold: float = 1_000_000
    window_hours: float = 48.0


class PredictionSnapshot(BaseModel):
    """Immutable prediction contract — never overwrite after creation."""

    id: str
    content_id: str | None = None
    model_id: str = "virality_predictor"
    model_version: str = "rule_v1"
    feature_version: str = "1"
    created_at: datetime | None = None
    predictions: dict[str, Any] = Field(default_factory=dict)
    # e.g. {"virality": {"probability": 0.78}, "engagement": {"probability": 0.72},
    #       "completion": {"probability": 0.65}, "share_rate": {"expected": 0.034},
    #       "views": {"expected": 1000000}}
    confidence: dict[str, Any] = Field(default_factory=dict)
    target: PredictionTarget = Field(default_factory=PredictionTarget)
    signals: dict[str, float] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    segments: dict[str, str] = Field(default_factory=dict)
    # platform, character, genre, hook_type, story_type
    registry_prediction_id: int | None = None


class ActualSnapshot(BaseModel):
    publication_id: str
    measurement_window: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    viral_state: str | None = None
    qa_score: float | None = None
    age_hours: float | None = None


class MetricVerification(BaseModel):
    metric: str
    predicted_value: float | None = None
    actual_value: float | None = None
    absolute_error: float | None = None
    relative_error: float | None = None
    log_error: float | None = None
    outcome: bool | None = None
    bias_direction: Literal["over", "under", "exact", "unknown"] = "unknown"


class RootCauseAnalysis(BaseModel):
    primary: dict[str, Any] = Field(default_factory=dict)
    contributing_factors: list[str] = Field(default_factory=list)
    prediction_model_error: dict[str, Any] = Field(default_factory=dict)
    taxonomy_codes: list[str] = Field(default_factory=list)
    note: str = "Association-based diagnosis; not causal proof"


class LearningSignalOut(BaseModel):
    signal_type: str
    signal_value: dict[str, Any]
    confidence: float = 0.5


class VerificationResultOut(BaseModel):
    verification_id: str
    prediction_ref: str
    publication_id: str | None
    stage: str
    status: str
    metrics: list[MetricVerification] = Field(default_factory=list)
    brier_score: float | None = None
    log_loss: float | None = None
    mape: float | None = None
    bias: float | None = None
    confidence_label: Literal[
        "correct", "incorrect", "overconfident", "underconfident", "unknown"
    ] = "unknown"
    diagnosis: RootCauseAnalysis | None = None
    learning_signals: list[LearningSignalOut] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class CreateVerificationRequest(BaseModel):
    publication_id: str | None = None
    prediction: PredictionSnapshot | dict[str, Any] | None = None
    prediction_ref: str | None = None
    registry_prediction_id: int | None = None
    stage: VerificationStage = "primary"
    process: bool = True
    # Optional overrides
    actuals: dict[str, Any] = Field(default_factory=dict)
    qa_score: float | None = None
    measurement_window_hours: float | None = None


class CompareModelsRequest(BaseModel):
    model_a: str
    model_b: str
    metric: str = "virality"
