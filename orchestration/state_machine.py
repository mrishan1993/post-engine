from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    CREATED = "created"
    SCRIPT_DONE = "script_done"
    AUDIO_DONE = "audio_done"
    VISUAL_DONE = "visual_done"
    ASSEMBLED = "assembled"
    QA_PENDING = "qa_pending"
    QA_APPROVED = "qa_approved"
    QA_REJECTED = "qa_rejected"
    PUBLISHED = "published"
    FAILED = "failed"


# Explicit allowed transitions. Publishing only from qa_approved.
ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.SCRIPT_DONE, RunStatus.FAILED},
    RunStatus.SCRIPT_DONE: {RunStatus.AUDIO_DONE, RunStatus.FAILED},
    RunStatus.AUDIO_DONE: {RunStatus.VISUAL_DONE, RunStatus.FAILED},
    RunStatus.VISUAL_DONE: {RunStatus.ASSEMBLED, RunStatus.FAILED},
    RunStatus.ASSEMBLED: {RunStatus.QA_PENDING, RunStatus.FAILED},
    RunStatus.QA_PENDING: {RunStatus.QA_APPROVED, RunStatus.QA_REJECTED, RunStatus.FAILED},
    RunStatus.QA_APPROVED: {RunStatus.PUBLISHED, RunStatus.FAILED},
    RunStatus.QA_REJECTED: {RunStatus.FAILED},  # regen creates a new row
    RunStatus.PUBLISHED: set(),
    RunStatus.FAILED: set(),
}

# Statuses from which automated pipeline stages may resume.
RESUME_FROM: dict[RunStatus, str] = {
    RunStatus.CREATED: "script",
    RunStatus.SCRIPT_DONE: "audio",
    RunStatus.AUDIO_DONE: "visual",
    RunStatus.VISUAL_DONE: "assembly",
    RunStatus.ASSEMBLED: "safety_qa",
    RunStatus.QA_APPROVED: "publishing",
}

STATUS_ORDER = [
    RunStatus.CREATED,
    RunStatus.SCRIPT_DONE,
    RunStatus.AUDIO_DONE,
    RunStatus.VISUAL_DONE,
    RunStatus.ASSEMBLED,
    RunStatus.QA_PENDING,
    RunStatus.QA_APPROVED,
    RunStatus.PUBLISHED,
]


def can_transition(current: str | RunStatus, target: str | RunStatus) -> bool:
    cur = RunStatus(current)
    tgt = RunStatus(target)
    return tgt in ALLOWED_TRANSITIONS.get(cur, set())


def assert_transition(current: str | RunStatus, target: str | RunStatus) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Illegal transition: {current} -> {target}")


def parse_regen_from(from_status: str) -> RunStatus:
    """Map --from flag to the status the new run should start at."""
    status = RunStatus(from_status)
    if status not in {
        RunStatus.CREATED,
        RunStatus.SCRIPT_DONE,
        RunStatus.AUDIO_DONE,
        RunStatus.VISUAL_DONE,
        RunStatus.ASSEMBLED,
    }:
        raise ValueError(
            f"regen --from must be one of created|script_done|audio_done|"
            f"visual_done|assembled, got {from_status}"
        )
    return status
