from __future__ import annotations

from performance_engine.schemas import DerivedMetrics, ViralState


def transition_viral_state(
    current: str,
    *,
    derived: DerivedMetrics,
    benchmark_p95_velocity: float,
    benchmark_p75_share_rate: float,
) -> ViralState:
    """Benchmark-relative viral state machine (V1 heuristic)."""
    vel = derived.view_velocity_per_hour
    share = derived.share_rate
    accel = derived.acceleration
    state = current or "normal"

    accelerating = vel > benchmark_p95_velocity and share >= benchmark_p75_share_rate
    viral = vel > benchmark_p95_velocity * 1.5 and share >= benchmark_p75_share_rate
    decelerating = accel < 0 and vel < benchmark_p95_velocity * 0.5
    plateau = abs(accel) < 100 and 0 < vel < benchmark_p95_velocity * 0.2

    if state == "normal":
        if accelerating:
            return "accelerating"
        return "normal"
    if state == "accelerating":
        if viral:
            return "viral"
        if decelerating:
            return "decelerating"
        return "accelerating"
    if state == "viral":
        if decelerating:
            return "peak"
        return "viral"
    if state == "peak":
        if decelerating or plateau:
            return "decelerating"
        if accelerating:
            return "second_wave"
        return "peak"
    if state == "decelerating":
        if accelerating:
            return "second_wave"
        if plateau:
            return "plateau"
        return "decelerating"
    if state == "plateau":
        if accelerating:
            return "second_wave"
        return "plateau"
    if state == "second_wave":
        if viral:
            return "viral"
        if decelerating:
            return "decelerating"
        return "second_wave"
    return "normal"  # type: ignore[return-value]


def major_dropoff(retention: list[dict]) -> dict | None:
    """Find largest retention cliff; attribution is probabilistic only."""
    if len(retention) < 2:
        return None
    worst = None
    for i in range(1, len(retention)):
        prev = float(retention[i - 1].get("retention_percent") or 0)
        cur = float(retention[i].get("retention_percent") or 0)
        drop = prev - cur
        if drop >= 8:  # percentage points
            cand = {
                "timestamp": float(retention[i].get("timestamp_sec") or 0),
                "severity": "high" if drop >= 15 else "medium",
                "drop_pp": round(drop, 2),
                "estimated_cause": "scene_change",  # heuristic label, not causal claim
            }
            if not worst or cand["drop_pp"] > worst["drop_pp"]:
                worst = cand
    return worst
