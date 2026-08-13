from __future__ import annotations

from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_predictive_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    """Signal only — never invents creative decisions; uses Probability Engine inputs."""
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    pred = package.prediction or {}
    virality = float(pred.get("virality_probability") or pred.get("virality") or 0.75)
    engagement = float(pred.get("engagement_probability") or pred.get("engagement") or 0.75)
    completion = float(pred.get("completion_probability") or pred.get("completion") or 0.7)
    score = round((virality + engagement + completion) / 3.0, 4)

    measurements.extend(
        [
            QaMeasurementSpec(
                dimension="predicted_quality",
                metric="virality_probability",
                value=virality,
                threshold=0.5,
                passed=virality >= 0.5,
            ),
            QaMeasurementSpec(
                dimension="predicted_quality",
                metric="engagement_probability",
                value=engagement,
                threshold=0.5,
                passed=engagement >= 0.5,
            ),
            QaMeasurementSpec(
                dimension="predicted_quality",
                metric="completion_probability",
                value=completion,
                threshold=0.45,
                passed=completion >= 0.45,
            ),
        ]
    )
    if score < 0.5:
        issues.append(
            QaIssueSpec(
                code="PREDICTED_QUALITY_LOW",
                severity="low",
                category="predictive",
                score=score,
                message=f"predicted quality {score:.2f} below soft threshold",
                recommended_action="review",
            )
        )

    return DimensionResult(
        dimension="predicted_quality",
        score=score,
        passed=True,  # never hard-fails publish alone
        issues=issues,
        measurements=measurements,
        notes=["predictive signal only; separate from correctness QA"],
    )
