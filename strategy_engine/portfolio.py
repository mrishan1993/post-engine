from __future__ import annotations

from collections import Counter
from typing import Any

from strategy_engine.schemas import StrategyProfile


def detect_content_debt(
    profile: StrategyProfile,
    planned_pillars: list[str | None],
    *,
    horizon_slots: int,
) -> dict[str, float]:
    """Negative values = under-served vs target mix."""
    mix = profile.content_mix or {}
    counts: Counter[str] = Counter()
    for p in planned_pillars:
        key = _norm_pillar(p)
        if key:
            counts[key] += 1
    debt: dict[str, float] = {}
    for pillar, target in mix.items():
        expected = target * horizon_slots
        actual = counts.get(pillar, 0)
        gap = actual - expected
        if gap < -0.5:
            debt[pillar] = round(gap, 2)
    return debt


def detect_saturation(
    recent_hooks: list[str],
    recent_pillars: list[str],
    recent_formats: list[str],
    *,
    max_same_hook_in_10: int = 3,
) -> list[str]:
    warnings: list[str] = []
    hooks = [h for h in recent_hooks if h]
    if hooks:
        top, n = Counter(hooks).most_common(1)[0]
        if n >= max_same_hook_in_10:
            warnings.append(f"Hook '{top}' used {n} times recently (limit {max_same_hook_in_10})")
    pillars = [p for p in recent_pillars if p]
    if pillars:
        top, n = Counter(pillars).most_common(1)[0]
        if n >= max(5, int(0.6 * len(pillars))):
            warnings.append(f"Pillar '{top}' over-concentrated ({n}/{len(pillars)})")
    formats = [f for f in recent_formats if f]
    if formats:
        top, n = Counter(formats).most_common(1)[0]
        if n >= max(6, int(0.75 * len(formats))):
            warnings.append(f"Format '{top}' repeated {n} times")
    return warnings


def mix_adherence(profile: StrategyProfile, planned_sources: list[str]) -> dict[str, Any]:
    mix = profile.content_mix or {}
    n = len(planned_sources) or 1
    counts = Counter(_norm_pillar(s) for s in planned_sources)
    actual = {k: round(v / n, 3) for k, v in counts.items()}
    deltas = {k: round(actual.get(k, 0) - float(mix.get(k, 0)), 3) for k in mix}
    return {"target": mix, "actual": actual, "deltas": deltas}


def apply_learning_to_mix(
    profile: StrategyProfile,
    learning_brief: dict[str, Any] | None,
) -> dict[str, float]:
    """Mild evidence-driven mix nudge — never extreme swings."""
    mix = dict(profile.content_mix or {})
    if not learning_brief:
        return mix
    recs = learning_brief.get("recommendations") or {}
    # If curiosity hooks preferred, nudge trend/character up slightly
    hook = recs.get("hook") or {}
    preferred = hook.get("preferred") or []
    if preferred:
        mix["trend"] = min(0.45, float(mix.get("trend", 0.3)) + 0.05)
        mix["evergreen"] = max(0.15, float(mix.get("evergreen", 0.25)) - 0.03)
        mix["experiment"] = max(0.05, float(mix.get("experiment", 0.1)))
    # Renormalize
    total = sum(mix.values()) or 1.0
    return {k: round(v / total, 3) for k, v in mix.items()}


def capacity_slots(profile: StrategyProfile, days: int) -> int:
    per_day = int((profile.capacity or {}).get("reels_per_day") or (profile.cadence or {}).get("posts_per_day") or 2)
    weekly = int((profile.capacity or {}).get("reels_per_week") or 14)
    return min(per_day * days, max(1, int(weekly * days / 7)))


def _norm_pillar(value: str | None) -> str:
    if not value:
        return "evergreen"
    v = value.lower()
    if v in {"trends", "trending"}:
        return "trend"
    if v in {"educational", "edu"}:
        return "education"
    if v in {"experimental"}:
        return "experiment"
    return v
