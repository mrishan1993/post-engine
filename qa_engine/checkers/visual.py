from __future__ import annotations

from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_visual_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    """V1: deterministic heuristic from timeline/spec + injected issues (vision cascade later)."""
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    score = 0.93
    tracks = (package.timeline or {}).get("tracks") or []
    has_video = any(t.get("type") == "video" for t in tracks)
    has_image = any(t.get("type") == "image" for t in tracks)
    measurements.append(
        QaMeasurementSpec(
            dimension="visual",
            metric="has_visual_track",
            value=1.0 if (has_video or has_image or package.storage_uri) else 0.0,
            threshold=1.0,
            passed=bool(has_video or has_image or package.storage_uri),
        )
    )
    if not (has_video or has_image or package.storage_uri):
        issues.append(
            QaIssueSpec(
                code="VISUAL_ARTIFACT",
                severity="critical",
                category="visual",
                message="no visual track in assembly",
                recommended_action="regenerate",
            )
        )
        score = 0.2

    for inj in package.injected_issues:
        if inj.category == "visual" or inj.code in {"VISUAL_ARTIFACT"}:
            issues.append(inj)
            if inj.severity in {"high", "critical"}:
                score = min(score, float(inj.score or 0.55))

    return DimensionResult(
        dimension="visual",
        score=round(score, 4),
        passed=score >= 0.7 and not any(i.severity == "critical" for i in issues),
        issues=issues,
        measurements=measurements,
        notes=["vision cascade stub — frame sampling reserved for V2"],
    )
