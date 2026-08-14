from __future__ import annotations

from orchestration_engine.schemas import JobStatus


# Linear happy-path stages (subset used for resume)
PIPELINE_ORDER: list[JobStatus] = [
    "DISCOVERED",
    "EVALUATING",
    "ACTIONABLE",
    "CONCEPT_GENERATING",
    "CONCEPT_SELECTED",
    "BRIEF_CREATED",
    "STORY_GENERATING",
    "STORYBOARD_GENERATING",
    "ASSET_GENERATING",
    "ASSEMBLING",
    "QA",
    "APPROVED",
    "PUBLISHING",
    "PUBLISHED",
    "MEASURING",
    "LEARNING",
]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DISCOVERED": {"EVALUATING", "FAILED", "CANCELLED"},
    "EVALUATING": {"ACTIONABLE", "WATCHING", "REJECTED", "FAILED", "AWAITING_APPROVAL", "CANCELLED"},
    "ACTIONABLE": {"CONCEPT_GENERATING", "AWAITING_APPROVAL", "FAILED", "CANCELLED"},
    "WATCHING": {"EVALUATING", "ACTIONABLE", "REJECTED", "CANCELLED"},
    "REJECTED": set(),
    "CONCEPT_GENERATING": {"CONCEPT_SELECTED", "FAILED", "CANCELLED"},
    "CONCEPT_SELECTED": {"BRIEF_CREATED", "AWAITING_APPROVAL", "FAILED", "CANCELLED"},
    "BRIEF_CREATED": {"STORY_GENERATING", "AWAITING_APPROVAL", "FAILED", "CANCELLED"},
    "STORY_GENERATING": {"STORYBOARD_GENERATING", "FAILED", "CANCELLED"},
    "STORYBOARD_GENERATING": {"ASSET_GENERATING", "FAILED", "CANCELLED"},
    "ASSET_GENERATING": {"ASSEMBLING", "FAILED", "CANCELLED"},
    "ASSEMBLING": {"QA", "FAILED", "CANCELLED"},
    "QA": {"APPROVED", "FAILED", "CANCELLED", "AWAITING_APPROVAL"},
    "APPROVED": {"PUBLISHING", "AWAITING_APPROVAL", "FAILED", "CANCELLED"},
    "PUBLISHING": {"PUBLISHED", "FAILED", "CANCELLED"},
    "PUBLISHED": {"MEASURING", "FAILED"},
    "MEASURING": {"LEARNING", "FAILED"},
    "LEARNING": set(),
    "AWAITING_APPROVAL": {
        "ACTIONABLE",
        "CONCEPT_GENERATING",
        "CONCEPT_SELECTED",
        "BRIEF_CREATED",
        "STORY_GENERATING",
        "APPROVED",
        "PUBLISHING",
        "FAILED",
        "CANCELLED",
    },
    "FAILED": {"DISCOVERED", "EVALUATING", "ACTIONABLE", "CONCEPT_GENERATING", "STORY_GENERATING", "CANCELLED"},
    "CANCELLED": set(),
}

# Resume mapping: last_successful_stage → next stage to run
RESUME_FROM: dict[str, str] = {
    "DISCOVERED": "EVALUATING",
    "EVALUATING": "ACTIONABLE",
    "ACTIONABLE": "CONCEPT_GENERATING",
    "CONCEPT_SELECTED": "BRIEF_CREATED",
    "BRIEF_CREATED": "STORY_GENERATING",
    "STORY_GENERATING": "STORYBOARD_GENERATING",
    "STORYBOARD_GENERATING": "ASSET_GENERATING",
    "ASSET_GENERATING": "ASSEMBLING",
    "ASSEMBLING": "QA",
    "QA": "APPROVED",
    "APPROVED": "PUBLISHING",
    "PUBLISHED": "MEASURING",
    "MEASURING": "LEARNING",
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


def transition(from_status: str, to_status: str) -> str:
    if not can_transition(from_status, to_status):
        raise ValueError(f"invalid orchestration transition {from_status} → {to_status}")
    return to_status


def next_pipeline_stage(current: str) -> str | None:
    if current not in PIPELINE_ORDER:
        return RESUME_FROM.get(current)
    idx = PIPELINE_ORDER.index(current)  # type: ignore[arg-type]
    if idx + 1 >= len(PIPELINE_ORDER):
        return None
    return PIPELINE_ORDER[idx + 1]
