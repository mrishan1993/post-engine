from __future__ import annotations


ALLOWED: dict[str, set[str]] = {
    "queued": {"validating", "cancelled"},
    "validating": {"routing", "failed"},
    "routing": {"preparing_references", "failed"},
    "preparing_references": {"submitting", "failed"},
    "submitting": {"processing", "failed"},
    "processing": {"downloading", "failed", "retry"},
    "downloading": {"validating_artifact", "failed"},
    "validating_artifact": {"completed", "failed"},
    "completed": set(),
    "retry": {"routing", "failed_permanently"},
    "fallback": {"routing", "failed_permanently"},
    "failed": {"retry", "fallback", "failed_permanently", "cancelled"},
    "failed_permanently": set(),
    "cancelled": set(),
}


def can_transition(current: str, new: str) -> bool:
    if current == new:
        return True
    return new in ALLOWED.get(current, set())


def transition(current: str, new: str) -> str:
    if not can_transition(current, new):
        raise ValueError(f"invalid video job transition {current} → {new}")
    return new
