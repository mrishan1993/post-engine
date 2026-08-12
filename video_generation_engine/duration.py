from __future__ import annotations

from typing import Any

from video_generation_engine.capabilities import get_video_provider_meta
from video_generation_engine.schemas import DurationStrategy


def resolve_duration(
    requested: float,
    provider_id: str,
    *,
    strategy: DurationStrategy = "nearest",
) -> dict[str, Any]:
    """Explicit duration adaptation — never silent."""
    meta = get_video_provider_meta(provider_id) or {}
    limits = meta.get("limits") or {}
    supported = [float(x) for x in (limits.get("supported_durations") or [])]
    min_d = float(limits.get("min_duration_sec") or 1)
    max_d = float(limits.get("max_duration_sec") or 30)

    if not supported:
        supported = [min_d, max_d]

    if requested in supported or any(abs(requested - s) < 0.05 for s in supported):
        chosen = min(supported, key=lambda s: abs(s - requested))
        return {
            "requested": requested,
            "resolved": chosen,
            "strategy": "exact",
            "changed": abs(chosen - requested) >= 0.05,
            "reason": None,
        }

    if strategy == "truncate":
        candidates = [s for s in supported if s <= requested]
        chosen = max(candidates) if candidates else min(supported)
        reason = "truncate_to_supported"
    elif strategy == "extend":
        candidates = [s for s in supported if s >= requested]
        chosen = min(candidates) if candidates else max(supported)
        reason = "extend_to_supported"
    else:
        chosen = min(supported, key=lambda s: abs(s - requested))
        reason = "nearest_supported"

    chosen = max(min_d, min(max_d, chosen))
    return {
        "requested": requested,
        "resolved": chosen,
        "strategy": strategy,
        "changed": True,
        "reason": reason,
    }
