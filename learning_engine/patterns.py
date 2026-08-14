from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from amp_platform.events import EventType, get_bus
from learning_engine.policy import evidence_confidence, evidence_status
from learning_engine.schemas import PatternStat, ScopeSpec
from db.models import LearningObservation


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.median(vals))


def _metric(obs: LearningObservation, metric: str) -> float | None:
    v = (obs.outcome_vector or {}).get(metric)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _feature(obs: LearningObservation, key: str) -> str | None:
    v = (obs.feature_vector or {}).get(key)
    if v is None or v == "":
        return None
    return str(v)


def analyze_dimension(
    observations: list[LearningObservation],
    *,
    dimension: str,
    metric: str = "completion_rate",
    min_group: int = 3,
) -> list[PatternStat]:
    groups: dict[str, list[float]] = defaultdict(list)
    all_vals: list[float] = []
    for obs in observations:
        key = _feature(obs, dimension)
        val = _metric(obs, metric)
        if key is None or val is None:
            continue
        groups[key].append(val)
        all_vals.append(val)

    baseline = _median(all_vals)
    if baseline is None or baseline == 0:
        baseline = 0.0

    patterns: list[PatternStat] = []
    for value, vals in sorted(groups.items(), key=lambda x: -(_median(x[1]) or 0)):
        if len(vals) < min_group:
            continue
        med = _median(vals) or 0.0
        lift = (med - baseline) / baseline if baseline else (1.0 if med > 0 else 0.0)
        n = len(vals)
        status = evidence_status(n)
        conf = evidence_confidence(n, lift)
        patterns.append(
            PatternStat(
                dimension=dimension,
                value=value,
                sample_size=n,
                median_metric=round(med, 6),
                baseline_median=round(baseline, 6),
                lift=round(lift, 4),
                evidence_status=status,
                confidence=conf,
            )
        )
    return patterns


def analyze_patterns(
    observations: list[LearningObservation],
    *,
    scope: ScopeSpec | None = None,
    metric: str = "completion_rate",
) -> list[PatternStat]:
    rows = observations
    if scope:
        if scope.character:
            rows = [o for o in rows if _feature(o, "character") == scope.character]
        if scope.platform:
            rows = [o for o in rows if _feature(o, "platform") == scope.platform]

    dims = (
        "hook_type",
        "story_type",
        "character",
        "trend_category",
        "duration_bucket",
        "platform",
    )
    out: list[PatternStat] = []
    for dim in dims:
        out.extend(analyze_dimension(rows, dimension=dim, metric=metric))

    # Hour-of-day if present
    out.extend(analyze_dimension(rows, dimension="hour", metric=metric, min_group=2))

    if out:
        get_bus().publish(
            EventType.PATTERN_DETECTED,
            {
                "pattern_count": len(out),
                "observation_count": len(rows),
                "metric": metric,
                "top": [
                    {"dimension": p.dimension, "value": p.value, "lift": p.lift}
                    for p in sorted(out, key=lambda x: -x.lift)[:5]
                ],
            },
            producer="learning-engine",
        )
    return out


def character_profile(observations: list[LearningObservation], character: str) -> dict[str, Any]:
    rows = [o for o in observations if _feature(o, "character") == character]
    if not rows:
        return {"character_id": character, "sample_size": 0}

    def med(metric: str) -> float | None:
        vals = [v for o in rows if (v := _metric(o, metric)) is not None]
        return _median(vals)

    hooks = analyze_dimension(rows, dimension="hook_type", metric="completion_rate", min_group=2)
    stories = analyze_dimension(rows, dimension="story_type", metric="completion_rate", min_group=2)
    durations = analyze_dimension(rows, dimension="duration_bucket", metric="completion_rate", min_group=2)

    # Fatigue heuristic: compare first third vs last third by created_at
    ordered = sorted(rows, key=lambda o: o.created_at or datetime_min())
    fatigue = None
    if len(ordered) >= 9:
        third = max(1, len(ordered) // 3)
        early = [_metric(o, "share_rate") for o in ordered[:third]]
        late = [_metric(o, "share_rate") for o in ordered[-third:]]
        early_m = _median([x for x in early if x is not None])
        late_m = _median([x for x in late if x is not None])
        if early_m and late_m and late_m < early_m * 0.75:
            fatigue = {
                "signal": "CHARACTER_FATIGUE",
                "early_median_share_rate": early_m,
                "late_median_share_rate": late_m,
                "note": "Associative decline; control for trend/story before concluding",
                "evidence_status": evidence_status(len(ordered)),
            }

    return {
        "character_id": character,
        "sample_size": len(rows),
        "median_views": med("views"),
        "median_share_rate": med("share_rate"),
        "median_completion": med("completion_rate"),
        "strengths": {
            "hooks": [p.model_dump() for p in hooks[:3] if p.lift > 0],
            "genres": [p.model_dump() for p in stories[:3] if p.lift > 0],
            "duration": [p.model_dump() for p in durations[:2] if p.lift > 0],
        },
        "weak_patterns": [p.model_dump() for p in hooks if p.lift < -0.1][:3],
        "fatigue": fatigue,
    }


def datetime_min():
    from datetime import datetime, timezone

    return datetime.min.replace(tzinfo=timezone.utc)


def trend_conversion(observations: list[LearningObservation]) -> list[dict[str, Any]]:
    """Trend predicted vs actual conversion — association only."""
    groups: dict[str, list[tuple[float | None, float | None]]] = defaultdict(list)
    for obs in observations:
        cat = _feature(obs, "trend_category")
        if not cat:
            continue
        pred = (obs.feature_vector or {}).get("predicted_virality")
        actual = _metric(obs, "virality_score")
        try:
            pred_f = float(pred) if pred is not None else None
        except (TypeError, ValueError):
            pred_f = None
        groups[cat].append((pred_f, actual))

    out = []
    for cat, pairs in groups.items():
        preds = [p for p, _ in pairs if p is not None]
        acts = [a for _, a in pairs if a is not None]
        if len(acts) < 3:
            continue
        mean_pred = sum(preds) / len(preds) if preds else None
        mean_act = sum(acts) / len(acts)
        adjustment = None
        label = "ALIGNED"
        if mean_pred is not None:
            adjustment = round(mean_act - mean_pred, 4)
            if adjustment < -0.1:
                label = "TREND_OVERPREDICTED"
            elif adjustment > 0.1:
                label = "TREND_UNDERPREDICTED"
        out.append(
            {
                "trend_category": cat,
                "sample_size": len(acts),
                "predicted_conversion": mean_pred,
                "actual_conversion": mean_act,
                "adjustment": adjustment,
                "label": label,
                "evidence_status": evidence_status(len(acts)),
                "note": "Association; feeds Trend Engine as candidate adjustment only",
            }
        )
    return out
