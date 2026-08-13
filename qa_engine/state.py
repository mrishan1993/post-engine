from __future__ import annotations


RUN_ALLOWED: dict[str, set[str]] = {
    "queued": {"running", "failed", "cancelled"},
    "running": {"completed", "failed", "review_required"},
    "completed": {"review_required"},
    "review_required": {"completed", "failed"},
    "failed": {"queued"},
    "cancelled": set(),
}


def can_transition(current: str, new: str) -> bool:
    if current == new:
        return True
    return new in RUN_ALLOWED.get(current, set())


def transition_run(current: str, new: str) -> str:
    if not can_transition(current, new):
        raise ValueError(f"invalid qa run transition {current} → {new}")
    return new
