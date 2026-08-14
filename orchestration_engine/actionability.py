from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from orchestration_engine.schemas import Actionability, ActionabilityThresholds, TrendOpportunityIn


def assess_actionability(
    opportunity: TrendOpportunityIn,
    *,
    thresholds: ActionabilityThresholds | None = None,
    brand_relevance: float = 0.75,
    character_relevance: float = 0.75,
    publishing_capacity: float = 1.0,
) -> tuple[Actionability, dict[str, Any]]:
    t = thresholds or ActionabilityThresholds()
    score = float(opportunity.opportunity_score)
    vel = float(opportunity.velocity_score)
    fresh = float(opportunity.freshness_score)
    sat = float(opportunity.saturation_score)
    stage = (opportunity.trend_stage or "").lower()

    reasons: list[str] = []
    if sat >= t.reject_saturation or stage in {"saturated", "declining", "dead"}:
        reasons.append(f"saturation={sat:.2f} stage={stage}")
        return "REJECT", {"reasons": reasons, "thresholds": t.model_dump()}
    if score < t.reject_score_below:
        reasons.append(f"opportunity_score={score:.2f} below reject floor")
        return "REJECT", {"reasons": reasons, "thresholds": t.model_dump()}

    act_ok = (
        score >= t.min_act_score
        and vel >= t.min_act_velocity
        and fresh >= t.min_act_freshness
        and sat <= t.max_act_saturation
        and brand_relevance >= 0.5
        and character_relevance >= 0.5
        and publishing_capacity > 0
    )
    if act_ok and stage in {"accelerating", "growing", "emerging", "peak", ""}:
        reasons.append("high velocity/freshness, low saturation, strong fit")
        return "ACT", {
            "reasons": reasons,
            "inputs": {
                "score": score,
                "velocity": vel,
                "freshness": fresh,
                "saturation": sat,
                "brand_relevance": brand_relevance,
                "character_relevance": character_relevance,
            },
            "thresholds": t.model_dump(),
        }

    reasons.append("promising but below ACT thresholds or early lifecycle")
    return "WATCH", {
        "reasons": reasons,
        "inputs": {
            "score": score,
            "velocity": vel,
            "freshness": fresh,
            "saturation": sat,
        },
        "thresholds": t.model_dump(),
    }


def compute_priority(opportunity: TrendOpportunityIn) -> float:
    """Priority = opportunity × freshness × expected_impact × time_sensitivity."""
    impact = max(opportunity.velocity_score, opportunity.opportunity_score)
    # Higher saturation → less time left; accelerating → more urgency
    time_sens = 1.0 - min(0.9, float(opportunity.saturation_score))
    if (opportunity.trend_stage or "").lower() in {"accelerating", "emerging"}:
        time_sens = min(1.0, time_sens + 0.15)
    return round(
        float(opportunity.opportunity_score)
        * float(opportunity.freshness_score)
        * float(impact)
        * float(time_sens),
        4,
    )


def estimate_expiration(opportunity: TrendOpportunityIn, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    stage = (opportunity.trend_stage or "").lower()
    hours = {
        "emerging": 36,
        "accelerating": 18,
        "growing": 24,
        "peak": 12,
        "declining": 4,
        "saturated": 1,
    }.get(stage, 24)
    # Faster expiry when saturation high
    hours = max(2.0, hours * (1.0 - 0.5 * float(opportunity.saturation_score)))
    return now + timedelta(hours=hours)


def opportunity_from_score_row(row: Any) -> TrendOpportunityIn:
    payload = row.opportunity or {}
    breakdown = row.score_breakdown or {}
    score01 = float(row.score or 0) / 100.0 if float(row.score or 0) > 1 else float(row.score or 0)
    vel = float(
        breakdown.get("growth")
        or breakdown.get("velocity")
        or payload.get("velocity_score")
        or score01
    )
    if vel > 1:
        vel = vel / 100.0
    sat = 0.8 if (row.lifecycle_stage or "").lower() == "saturated" else float(
        payload.get("saturation_score") or breakdown.get("saturation") or 0.25
    )
    if sat > 1:
        sat = sat / 100.0
    fresh = float(payload.get("freshness_score") or breakdown.get("freshness") or (1.0 - sat * 0.5))
    if fresh > 1:
        fresh = fresh / 100.0
    mechanism = (
        payload.get("viral_mechanism")
        or payload.get("why_viral")
        or payload.get("hook_type")
        or row.pattern_key
        or "curiosity_gap"
    )
    return TrendOpportunityIn(
        trend_id=f"opp_{row.id}",
        platform=str(payload.get("platform") or "instagram"),
        trend_stage=str(row.lifecycle_stage or payload.get("lifecycle") or "accelerating"),
        velocity_score=vel,
        freshness_score=fresh,
        saturation_score=sat,
        opportunity_score=score01 if score01 <= 1 else score01 / 100.0,
        viral_mechanism=str(mechanism) if mechanism else None,
        format=str(payload.get("format") or "short_form_video"),
        title=row.title,
        audio=dict(payload.get("audio") or {}),
        audience=list(payload.get("audience") or ["gen_z"]),
        opportunity_id=row.id,
        vertical_slug=row.vertical_slug,
        pattern_key=row.pattern_key,
        raw={"opportunity": payload, "score_breakdown": breakdown},
    )
