from __future__ import annotations

from generation_engine.schemas import JobStatus


ALLOWED: dict[str, set[str]] = {
    "queued": {"validating", "cancelled"},
    "validating": {"routing", "failed"},
    "routing": {"submitted", "failed"},
    "submitted": {"processing", "failed"},
    "processing": {"completed", "failed", "retry"},
    "retry": {"routing", "failed_permanently"},
    "fallback": {"routing", "failed_permanently"},
    "failed": {"retry", "fallback", "failed_permanently", "cancelled"},
    "completed": {"qa_pending"},
    "qa_pending": {"approved", "failed"},
    "approved": set(),
    "failed_permanently": set(),
    "cancelled": set(),
}


def can_transition(current: str, new: str) -> bool:
    if current == new:
        return True
    return new in ALLOWED.get(current, set())


def transition(current: JobStatus | str, new: JobStatus | str) -> str:
    cur, nxt = str(current), str(new)
    if not can_transition(cur, nxt):
        raise ValueError(f"invalid job transition {cur} → {nxt}")
    return nxt
