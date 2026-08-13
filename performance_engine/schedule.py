from __future__ import annotations

# Snapshot ages (seconds) for the default collection schedule
DEFAULT_SNAPSHOT_AGES_SEC: list[int] = [
    5 * 60,
    15 * 60,
    30 * 60,
    60 * 60,
    2 * 60 * 60,
    6 * 60 * 60,
    12 * 60 * 60,
    24 * 60 * 60,
    48 * 60 * 60,
    72 * 60 * 60,
    7 * 24 * 60 * 60,
    14 * 24 * 60 * 60,
    30 * 24 * 60 * 60,
]


def poll_tier_for_age(age_sec: int) -> str:
    if age_sec < 2 * 3600:
        return "high"
    if age_sec < 24 * 3600:
        return "medium"
    if age_sec < 7 * 24 * 3600:
        return "low"
    return "archival"


def next_interval_sec(tier: str, *, accelerated: bool = False) -> int:
    base = {
        "high": 5 * 60,
        "medium": 30 * 60,
        "low": 6 * 3600,
        "archival": 24 * 3600,
    }.get(tier, 3600)
    if accelerated:
        return max(60, base // 4)
    return base
