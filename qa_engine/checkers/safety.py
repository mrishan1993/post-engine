from __future__ import annotations

from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_safety_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    """Hard-gated safety layer. V1 uses keyword/config heuristics + injected risk."""
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    risk = package.force_safety_risk or "none"
    score = 1.0

    text_blob = " ".join(
        [
            str(package.expected_script or ""),
            str((package.story or {}).get("synopsis") or ""),
            str((package.story or {}).get("title") or ""),
            " ".join(str(c.get("text") or "") for c in (package.captions or [])),
        ]
    ).lower()

    # Configurable high-risk tokens (content-policy stub)
    high_tokens = ["suicide method", "how to make a bomb", "child sexual"]
    medium_tokens = ["gore", "extreme violence"]
    for tok in high_tokens:
        if tok in text_blob:
            risk = "high"
    for tok in medium_tokens:
        if tok in text_blob and risk == "none":
            risk = "medium"

    # Provenance gate
    provenance = package.asset_provenance or {}
    for aid, meta in provenance.items():
        status = str((meta or {}).get("license_status") or "unknown")
        if status not in {"valid", "generated", "licensed", "ok"}:
            issues.append(
                QaIssueSpec(
                    code="UNKNOWN_PROVENANCE",
                    severity="critical",
                    category="safety",
                    artifact_id=str(aid),
                    message=f"asset {aid} license_status={status}",
                    recommended_action="block",
                )
            )
            risk = "high"
            score = 0.0

    risk_score = {"none": 1.0, "low": 0.9, "medium": 0.6, "high": 0.0}[risk]
    score = min(score, risk_score)
    measurements.append(
        QaMeasurementSpec(
            dimension="safety",
            metric="policy_risk",
            value=risk_score,
            threshold=0.9,
            passed=risk in {"none", "low"},
            metadata={"risk": risk},
        )
    )
    if risk in {"high"}:
        issues.append(
            QaIssueSpec(
                code="POLICY_VIOLATION",
                severity="critical",
                category="safety",
                message="policy risk HIGH — publish blocked",
                recommended_action="block",
            )
        )
    elif risk == "medium":
        issues.append(
            QaIssueSpec(
                code="POLICY_VIOLATION",
                severity="medium",
                category="safety",
                message="policy risk MEDIUM — human review required",
                recommended_action="review",
            )
        )

    for inj in package.injected_issues:
        if inj.category == "safety" or inj.code in {"POLICY_VIOLATION", "UNKNOWN_PROVENANCE"}:
            issues.append(inj)

    return DimensionResult(
        dimension="safety",
        score=round(score, 4),
        passed=risk in {"none", "low"},
        issues=issues,
        measurements=measurements,
        notes=[f"policy_risk={risk}"],
    )
