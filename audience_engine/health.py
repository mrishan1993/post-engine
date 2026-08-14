from __future__ import annotations

from typing import Any


def community_health_score(
    *,
    positive_ratio: float,
    participation_rate: float,
    returning_proxy: float,
    conversation_depth: float,
    diversity: float,
    toxicity: float,
    spam_rate: float,
    negative_trend: float,
) -> float:
    """Configurable community health (0–100). Exact weights are V1 heuristics."""
    raw = (
        25 * positive_ratio
        + 20 * participation_rate
        + 15 * returning_proxy
        + 15 * conversation_depth
        + 10 * diversity
        - 20 * toxicity
        - 15 * spam_rate
        - 15 * negative_trend
    )
    # shift into 0–100-ish with baseline
    score = 50 + raw
    return round(max(0.0, min(100.0, score)), 2)


def health_from_batch(
    interactions: list[dict[str, Any]],
    *,
    analytics: list[dict[str, Any]] | None = None,
) -> tuple[float, dict[str, Any], list[dict[str, Any]]]:
    clean = [i for i in interactions if not i.get("is_noise")]
    noise = [i for i in interactions if i.get("is_noise")]
    total = max(1, len(interactions))
    clean_n = max(1, len(clean))
    pos = sum(1 for i in clean if i.get("sentiment") == "positive") / clean_n
    neg = sum(1 for i in clean if i.get("sentiment") == "negative") / clean_n
    requests = sum(
        1
        for i in clean
        if i.get("intent_type") in {"content_request", "character_request", "participation"}
    )
    participation = min(1.0, requests / clean_n)
    depth = min(1.0, sum(1 for i in clean if len((i.get("text") or i.get("text_reference") or "")) > 40) / clean_n)
    langs = {i.get("language") for i in clean}
    diversity = min(1.0, len(langs) / 3.0)
    tox = sum(1 for i in clean if (i.get("moderation_flags") or [])) / clean_n
    spam = len(noise) / total
    returning = 0.5
    if analytics:
        rates = [float(a.get("returning_viewer_rate") or 0) for a in analytics if a.get("returning_viewer_rate")]
        if rates:
            returning = sum(rates) / len(rates)

    score = community_health_score(
        positive_ratio=pos,
        participation_rate=participation,
        returning_proxy=returning,
        conversation_depth=depth,
        diversity=diversity,
        toxicity=tox,
        spam_rate=spam,
        negative_trend=neg,
    )
    components = {
        "positive_ratio": round(pos, 3),
        "participation_rate": round(participation, 3),
        "returning_proxy": round(returning, 3),
        "conversation_depth": round(depth, 3),
        "diversity": round(diversity, 3),
        "toxicity": round(tox, 3),
        "spam_rate": round(spam, 3),
        "negative_trend": round(neg, 3),
    }
    alerts: list[dict[str, Any]] = []
    if score < 40:
        alerts.append(
            {
                "alert_type": "community_health_low",
                "severity": "P1",
                "subject": f"Community health at {score}",
                "evidence": components,
                "recommended_action": "increase_relationship_content",
            }
        )
    if neg > 0.35:
        alerts.append(
            {
                "alert_type": "sentiment_declining",
                "severity": "P1",
                "subject": "Negative discussion elevated",
                "evidence": {"negative_ratio": neg},
                "recommended_action": "review_character_narrative",
            }
        )
    if spam > 0.4:
        alerts.append(
            {
                "alert_type": "spam_spike",
                "severity": "P2",
                "subject": "Spam activity unusually high",
                "evidence": {"spam_rate": spam},
                "recommended_action": "escalate_moderation",
            }
        )
    return score, components, alerts
