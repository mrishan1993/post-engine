from __future__ import annotations

from qa_engine.schemas import QaDecision, QaIssueSpec, QaResult, QaThresholds
from qa_engine.routing import regeneration_targets_from_issues, repair_actions_from_issues, route_issue


SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def decide(
    *,
    content_id: str,
    dimension_scores: dict[str, float],
    issues: list[QaIssueSpec],
    thresholds: QaThresholds,
    policy_risk: str = "none",
) -> QaResult:
    routed = [route_issue(i.model_copy(deep=True)) for i in issues]

    # Weighted overall (safety weight kept for reporting; hard-gated separately)
    weights = thresholds.weights
    total_w = sum(weights.get(d, 0) for d in dimension_scores) or 1.0
    overall = sum(dimension_scores.get(d, 0) * weights.get(d, 0) for d in dimension_scores) / total_w
    overall = round(overall, 4)

    has_critical = any(i.severity == "critical" for i in routed)
    has_high_regen = any(
        i.severity in {"high", "critical"} and i.recommended_action == "regenerate" for i in routed
    )
    has_repair = any(i.recommended_action == "repair" and i.severity in {"medium", "high"} for i in routed)
    safety_score = dimension_scores.get("safety", 1.0)
    technical_score = dimension_scores.get("technical", 1.0)
    character_score = dimension_scores.get("character", 1.0)

    decision: QaDecision
    notes: list[str] = []

    if policy_risk in thresholds.safety_block_levels or any(
        i.code == "POLICY_VIOLATION" and i.severity == "critical" for i in routed
    ):
        decision = "block"
        notes.append("safety hard gate")
    elif policy_risk in thresholds.safety_review_levels or any(
        i.code == "POLICY_VIOLATION" and i.recommended_action == "review" for i in routed
    ):
        decision = "review_required"
        notes.append("safety medium risk requires human review")
    elif has_critical or technical_score < thresholds.technical_min_score * 0.5:
        # Catastrophic technical → block rather than silent regen loop
        if any(i.code in {"MISSING_FILE", "CORRUPT_MEDIA", "UNKNOWN_PROVENANCE"} for i in routed):
            decision = "block"
            notes.append("critical technical/provenance failure")
        else:
            decision = "regenerate"
            notes.append("critical failure → regenerate")
    elif has_high_regen or character_score < thresholds.character_min_score:
        decision = "regenerate"
        notes.append("high-severity generation defect")
    elif overall >= thresholds.pass_score and not has_repair and safety_score >= 0.9:
        decision = "pass"
    elif has_repair or overall >= thresholds.repair_score:
        # Prefer repair when only assembly-fixable issues
        if has_high_regen:
            decision = "regenerate"
        elif overall >= thresholds.pass_score and not has_repair:
            decision = "pass"
        else:
            only_repair = all(
                i.recommended_action in {"repair", "none", "review"}
                or i.severity in {"low", "info"}
                for i in routed
            )
            decision = "repair" if only_repair or has_repair else "regenerate"
            if decision == "repair":
                notes.append("deterministic repair available")
    else:
        decision = "regenerate"
        notes.append("overall score below repair threshold")

    return QaResult(
        content_id=content_id,
        decision=decision,
        overall_score=overall,
        dimensions=dimension_scores,
        issues=routed,
        policy_risk=policy_risk,  # type: ignore[arg-type]
        repair_actions=repair_actions_from_issues(routed),
        regeneration_targets=regeneration_targets_from_issues(routed),
        notes=notes,
    )
