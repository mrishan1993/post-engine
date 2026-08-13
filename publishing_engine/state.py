from __future__ import annotations


PLAN_ALLOWED: dict[str, set[str]] = {
    "draft": {"approved", "cancelled", "blocked"},
    "approved": {"scheduled", "queued", "publishing", "cancelled", "blocked"},
    "scheduled": {"queued", "publishing", "cancelled"},
    "queued": {"publishing", "cancelled"},
    "publishing": {"completed", "partial", "failed"},
    "completed": set(),
    "partial": {"publishing", "completed"},
    "failed": {"approved", "queued", "cancelled"},
    "blocked": {"draft", "cancelled"},
    "cancelled": set(),
}

JOB_ALLOWED: dict[str, set[str]] = {
    "draft": {"approved", "blocked", "cancelled"},
    "approved": {"scheduled", "queued", "blocked"},
    "scheduled": {"queued", "cancelled"},
    "queued": {"validating", "cancelled", "blocked"},
    "validating": {"uploading", "blocked", "failed"},
    "uploading": {"processing", "failed", "retry"},
    "processing": {"publishing", "failed", "retry"},
    "publishing": {"verifying", "failed", "retry"},
    "verifying": {"published", "failed", "retry"},
    "published": set(),
    "failed": {"retry", "cancelled", "blocked", "queued"},
    "retry": {"validating", "queued", "failed"},
    "blocked": {"cancelled"},
    "cancelled": set(),
}


def can_transition(allowed: dict[str, set[str]], current: str, new: str) -> bool:
    if current == new:
        return True
    return new in allowed.get(current, set())


def transition_plan(current: str, new: str) -> str:
    if not can_transition(PLAN_ALLOWED, current, new):
        raise ValueError(f"invalid plan transition {current} → {new}")
    return new


def transition_job(current: str, new: str) -> str:
    if not can_transition(JOB_ALLOWED, current, new):
        raise ValueError(f"invalid job transition {current} → {new}")
    return new
