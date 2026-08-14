from __future__ import annotations

from learning_engine.schemas import EvidenceStatus, OptimizationPolicy


DEFAULT_POLICY = OptimizationPolicy()


def evidence_status(sample_size: int, *, min_supported: int = 30, min_strong: int = 100) -> EvidenceStatus:
    if sample_size < min_supported:
        return "EXPLORATORY"
    if sample_size < min_strong:
        return "SUPPORTED"
    return "STRONG"


def evidence_confidence(sample_size: int, lift: float) -> float:
    """Heuristic confidence from n + effect size (not a p-value)."""
    n_factor = min(1.0, sample_size / 100.0)
    effect_factor = min(1.0, abs(lift) / 0.25)
    return round(0.35 + 0.40 * n_factor + 0.25 * effect_factor, 3)


def duration_bucket(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = float(seconds)
    if s < 15:
        return "0-15"
    if s < 20:
        return "15-20"
    if s < 25:
        return "20-25"
    if s < 30:
        return "25-30"
    if s < 45:
        return "30-45"
    return "45+"


def hour_bucket(hour: int | None) -> str | None:
    if hour is None:
        return None
    return f"{int(hour):02d}:00-{int(hour):02d}:59"


GUARDRAIL_FORBIDDEN_ACTIONS = frozenset(
    {
        "spam",
        "misleading_clickbait",
        "unsafe_content",
        "canon_violation",
        "excessive_posting",
        "manipulative_engagement",
    }
)


def is_guardrail_safe(action: str) -> bool:
    a = action.lower().replace(" ", "_")
    return a not in GUARDRAIL_FORBIDDEN_ACTIONS and not any(x in a for x in GUARDRAIL_FORBIDDEN_ACTIONS)
