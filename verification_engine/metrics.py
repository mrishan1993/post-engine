from __future__ import annotations

import math
from typing import Any

from verification_engine.schemas import MetricVerification


def absolute_error(predicted: float, actual: float) -> float:
    return abs(actual - predicted)


def relative_error(predicted: float, actual: float) -> float | None:
    if predicted == 0:
        return None
    return (actual - predicted) / abs(predicted)


def log_error(predicted: float, actual: float) -> float:
    return abs(math.log1p(actual) - math.log1p(predicted))


def mape(errors: list[float]) -> float | None:
    if not errors:
        return None
    return sum(errors) / len(errors)


def rmse(absolute_errors: list[float]) -> float | None:
    if not absolute_errors:
        return None
    return math.sqrt(sum(e**2 for e in absolute_errors) / len(absolute_errors))


def bias(predicted_actual_pairs: list[tuple[float, float]]) -> float | None:
    if not predicted_actual_pairs:
        return None
    return sum(p - a for p, a in predicted_actual_pairs) / len(predicted_actual_pairs)


def brier_score(probability: float, outcome: bool) -> float:
    y = 1.0 if outcome else 0.0
    return (probability - y) ** 2


def log_loss(probability: float, outcome: bool, *, eps: float = 1e-15) -> float:
    p = min(max(probability, eps), 1.0 - eps)
    y = 1.0 if outcome else 0.0
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def verify_metric(
    metric: str,
    predicted: float | None,
    actual: float | None,
    *,
    binary_threshold: float | None = None,
) -> MetricVerification:
    if predicted is None or actual is None:
        return MetricVerification(metric=metric, predicted_value=predicted, actual_value=actual)

    abs_err = absolute_error(predicted, actual)
    rel = relative_error(predicted, actual)
    log_err = log_error(predicted, actual)
    outcome = None
    if binary_threshold is not None:
        outcome = actual >= binary_threshold

    if rel is None:
        direction: str = "unknown"
    elif abs(rel) < 0.05:
        direction = "exact"
    elif rel > 0:
        direction = "under"  # actual > predicted → underpredicted
    else:
        direction = "over"

    return MetricVerification(
        metric=metric,
        predicted_value=round(predicted, 6),
        actual_value=round(actual, 6),
        absolute_error=round(abs_err, 6),
        relative_error=round(rel, 6) if rel is not None else None,
        log_error=round(log_err, 6),
        outcome=outcome,
        bias_direction=direction,  # type: ignore[arg-type]
    )


def spearman_rank(xs: list[float], ys: list[float]) -> float | None:
    """Simple Spearman ρ without scipy dependency."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    num = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    den_x = math.sqrt(sum((rx[i] - mean_x) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i] - mean_y) ** 2 for i in range(n)))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def extract_predicted_actual_pairs(
    prediction: dict[str, Any], actual_metrics: dict[str, Any]
) -> list[tuple[str, float | None, float | None, float | None]]:
    """Return list of (metric, predicted, actual, binary_threshold)."""
    preds = prediction.get("predictions") or {}
    pairs: list[tuple[str, float | None, float | None, float | None]] = []

    def _prob(key: str) -> float | None:
        node = preds.get(key)
        if node is None:
            return None
        if isinstance(node, (int, float)):
            return float(node)
        if isinstance(node, dict):
            for k in ("probability", "expected", "value"):
                if k in node and node[k] is not None:
                    return float(node[k])
        return None

    # Probabilities
    for key, actual_key, thr in (
        ("virality", "virality_score", 0.7),
        ("engagement", "engagement_rate", None),
        ("completion", "completion_rate", None),
    ):
        p = _prob(key)
        a = actual_metrics.get(actual_key)
        if a is None and key == "virality":
            # binary from viral state / views threshold handled separately
            a = actual_metrics.get("virality")
        pairs.append((key, p, float(a) if a is not None else None, thr if key == "virality" else None))

    # Continuous expected rates / volumes
    for key, actual_key in (
        ("share_rate", "share_rate"),
        ("views", "views"),
        ("saves", "saves"),
        ("likes", "likes"),
    ):
        p = _prob(key)
        a = actual_metrics.get(actual_key)
        pairs.append((key, p, float(a) if a is not None else None, None))

    # Target-based binary for views if target present
    target = prediction.get("target") or {}
    if target.get("metric") == "views" and target.get("threshold") is not None:
        thr = float(target["threshold"])
        p = _prob("virality") or prediction.get("confidence", {}).get("overall")
        views = actual_metrics.get("views")
        if views is not None:
            # Replace/augment virality outcome with window success
            pairs.append(("viral_target", float(p) if p is not None else None, float(views), thr))

    return pairs
