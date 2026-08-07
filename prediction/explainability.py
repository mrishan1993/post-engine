from __future__ import annotations

from typing import Any

from prediction.features import FeatureVector

POSITIVE_LABELS = {
    "hook_strength": "Strong hook",
    "trend_velocity": "Fast-growing trend / high velocity",
    "lifecycle_score": "Favorable trend lifecycle",
    "curiosity_score": "High curiosity pull",
    "fear_score": "High emotional intensity (fear)",
    "joy_score": "High emotional intensity (joy)",
    "novelty": "Novel pattern vs saturated formats",
    "character_fit": "Excellent character fit",
    "audience_fit": "Audience fit",
    "cross_platform": "Cross-platform confirmation",
    "posting_fit": "Good posting window",
    "similar_winners": "Similar to previous winners",
    "character_familiarity": "Familiar character",
    "brand_fit": "Brand / vertical fit",
}

NEGATIVE_LABELS = {
    "competition": "High competition",
    "story_complexity": "Complex story for short format",
}


def build_reasoning(
    features: FeatureVector,
    *,
    virality: float,
    confidence: float,
) -> dict[str, Any]:
    scored = []
    for name, value in features.values.items():
        if name in NEGATIVE_LABELS:
            # Higher competition is more negative
            scored.append((name, value, "negative" if value > 0.55 else "neutral"))
        elif name in POSITIVE_LABELS:
            scored.append((name, value, "positive" if value >= 0.65 else "neutral"))

    positives = sorted(
        [(n, v) for n, v, kind in scored if kind == "positive"],
        key=lambda x: x[1],
        reverse=True,
    )[:5]
    negatives = sorted(
        [(n, v) for n, v, kind in scored if kind == "negative"],
        key=lambda x: x[1],
        reverse=True,
    )[:4]

    similar = int(features.get("similar_winners") * 20)
    reasons = []
    for name, value in positives:
        reasons.append(f"{POSITIVE_LABELS.get(name, name)} ({value:.2f})")
    if similar >= 3:
        reasons.append(f"Similar to {similar} previous winners")

    neg_reasons = [f"{NEGATIVE_LABELS.get(n, n)} ({v:.2f})" for n, v in negatives]
    if features.get("lifecycle_score") < 0.3:
        neg_reasons.append("Trend lifecycle weak / late")

    return {
        "virality_probability": round(virality, 4),
        "confidence": round(confidence, 4),
        "top_positive_signals": [POSITIVE_LABELS.get(n, n) for n, _ in positives],
        "top_negative_signals": [NEGATIVE_LABELS.get(n, n) for n, _ in negatives],
        "positive_detail": reasons,
        "negative_detail": neg_reasons,
        "summary": (
            f"Virality {virality:.0%} with {confidence:.0%} confidence. "
            + (
                f"Driven by {', '.join(POSITIVE_LABELS.get(n, n) for n, _ in positives[:3])}."
                if positives
                else "Limited positive signal."
            )
        ),
        "feature_snapshot": dict(features.values),
        "context": dict(features.raw),
    }


def format_explanation(reasoning: dict[str, Any]) -> str:
    lines = [
        f"Virality Probability: {float(reasoning.get('virality_probability', 0)):.0%}",
        f"Confidence: {float(reasoning.get('confidence', 0)):.0%}",
        "",
        "Top Positive Signals:",
    ]
    for s in reasoning.get("top_positive_signals") or []:
        lines.append(f"  + {s}")
    lines.append("")
    lines.append("Top Negative Signals:")
    negs = reasoning.get("top_negative_signals") or []
    if not negs:
        lines.append("  (none significant)")
    for s in negs:
        lines.append(f"  - {s}")
    lines.append("")
    lines.append(reasoning.get("summary") or "")
    return "\n".join(lines)
