from __future__ import annotations

from performance_engine.schemas import (
    CanonicalMetrics,
    DerivedMetrics,
    EngagementWeights,
    ViralityWeights,
)


def _safe_div(n: float, d: float) -> float:
    if not d:
        return 0.0
    return float(n) / float(d)


def compute_derived(
    metrics: CanonicalMetrics,
    *,
    prev_views: int | None = None,
    prev_shares: int | None = None,
    prev_velocity: float | None = None,
    delta_hours: float | None = None,
    engagement_weights: EngagementWeights | None = None,
    virality_weights: ViralityWeights | None = None,
) -> DerivedMetrics:
    ew = engagement_weights or EngagementWeights()
    vw = virality_weights or ViralityWeights()
    views = max(int(metrics.views or 0), 0)
    likes = int(metrics.likes or 0)
    comments = int(metrics.comments or 0)
    shares = int(metrics.shares or 0)
    saves = int(metrics.saves or 0)
    follows = int(metrics.followers_gained or 0)

    like_rate = _safe_div(likes, views)
    comment_rate = _safe_div(comments, views)
    share_rate = _safe_div(shares, views)
    save_rate = _safe_div(saves, views)
    engagement_rate = _safe_div(likes + comments + shares + saves, views)
    weighted = _safe_div(
        likes * ew.like
        + comments * ew.comment
        + saves * ew.save
        + shares * ew.share
        + follows * ew.follow,
        views,
    )

    view_velocity = 0.0
    share_velocity = 0.0
    acceleration = 0.0
    if delta_hours and delta_hours > 0 and prev_views is not None:
        view_velocity = (views - prev_views) / delta_hours
        share_velocity = (shares - (prev_shares or 0)) / delta_hours
        if prev_velocity is not None:
            acceleration = (view_velocity - prev_velocity) / delta_hours

    # Normalize components into 0-1-ish scores for virality model v1
    share_comp = min(1.0, share_rate / 0.05)  # 5% share rate ≈ 1.0
    vel_comp = min(1.0, view_velocity / 100_000)  # 100k views/hour ≈ 1.0
    nfr = metrics.non_follower_reach
    reach = metrics.reach or views
    nfr_comp = min(1.0, _safe_div(nfr or 0, reach)) if nfr is not None else 0.5
    completion = float(metrics.completion_rate or 0.0)
    rewatch = 0.0
    if metrics.unique_viewers and metrics.unique_viewers > 0 and views:
        rewatch = min(1.0, max(0.0, (views / metrics.unique_viewers) - 1.0))
    else:
        rewatch = 0.0  # UNAVAILABLE → contribute 0, not invented
    eng_comp = min(1.0, engagement_rate / 0.15)

    virality = (
        vw.share_rate * share_comp
        + vw.view_velocity * vel_comp
        + vw.non_follower_reach * nfr_comp
        + vw.completion * completion
        + vw.rewatch * rewatch
        + vw.engagement * eng_comp
    )

    return DerivedMetrics(
        like_rate=round(like_rate, 6),
        comment_rate=round(comment_rate, 6),
        share_rate=round(share_rate, 6),
        save_rate=round(save_rate, 6),
        engagement_rate=round(engagement_rate, 6),
        weighted_engagement=round(weighted, 6),
        virality_score=round(min(1.0, max(0.0, virality)), 6),
        view_velocity_per_hour=round(view_velocity, 4),
        share_velocity_per_hour=round(share_velocity, 4),
        acceleration=round(acceleration, 4),
        engagement_formula_version=ew.version,
        virality_model_version=vw.version,
    )


def performance_vector(metrics: CanonicalMetrics, derived: DerivedMetrics) -> dict[str, float]:
    views_norm = min(1.0, (metrics.views or 0) / 1_000_000)
    return {
        "distribution": round(views_norm, 4),
        "engagement": round(min(1.0, derived.engagement_rate / 0.15), 4),
        "retention": round(float(metrics.completion_rate or 0), 4),
        "sharing": round(min(1.0, derived.share_rate / 0.05), 4),
        "conversion": round(
            min(
                1.0,
                ((metrics.followers_gained or 0) / max(metrics.profile_visits or 1, 1)),
            ),
            4,
        ),
        "virality": round(derived.virality_score, 4),
    }
