from __future__ import annotations

from pathlib import Path

from assembly_engine.profiles import get_platform_profile
from assembly_engine.validation import probe_media, validate_rendered_output
from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_technical_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    uri = package.storage_uri
    if not uri or not Path(uri).exists():
        issues.append(
            QaIssueSpec(
                code="MISSING_FILE",
                severity="critical",
                category="technical",
                message="Final artifact file missing",
                recommended_action="block",
            )
        )
        return DimensionResult(dimension="technical", score=0.0, passed=False, issues=issues)

    profile = get_platform_profile(package.platform_profile)
    canvas = profile["canvas"]
    expected_w = package.width or canvas.width
    expected_h = package.height or canvas.height
    expected_fps = package.fps or canvas.fps
    expected_dur = package.duration_sec or float(
        (package.specification or {}).get("duration_sec") or 30
    )

    # Prefer prior assembly technical_qa if present and ok
    prior = package.technical_qa or {}
    tech = validate_rendered_output(
        uri,
        expected_duration=float(expected_dur),
        expected_width=int(expected_w),
        expected_height=int(expected_h),
        expected_fps=float(expected_fps),
    )
    probed = tech.probed or probe_media(uri)

    def _m(metric: str, value: float | None, threshold: float | None, passed: bool, **meta):
        measurements.append(
            QaMeasurementSpec(
                dimension="technical",
                metric=metric,
                value=value,
                threshold=threshold,
                passed=passed,
                metadata=meta,
            )
        )

    _m("resolution_w", float(probed.get("width") or 0), float(expected_w), tech.resolution_ok)
    _m("resolution_h", float(probed.get("height") or 0), float(expected_h), tech.resolution_ok)
    _m("fps", float(probed.get("fps") or 0) if probed.get("fps") else None, float(expected_fps), tech.fps_ok)
    _m(
        "duration_sec",
        float(probed.get("duration_sec") or 0) if probed.get("duration_sec") else None,
        float(expected_dur),
        tech.duration_ok,
    )

    if not tech.resolution_ok:
        issues.append(
            QaIssueSpec(
                code="INVALID_RESOLUTION",
                severity="high",
                category="technical",
                message="; ".join(tech.notes) or "resolution mismatch",
                recommended_action="repair",
            )
        )
    if not tech.fps_ok:
        issues.append(
            QaIssueSpec(
                code="INVALID_FPS",
                severity="medium",
                category="technical",
                message="fps mismatch",
                recommended_action="repair",
            )
        )
    if not tech.duration_ok:
        issues.append(
            QaIssueSpec(
                code="INVALID_DURATION",
                severity="high",
                category="technical",
                message="duration mismatch",
                recommended_action="repair",
            )
        )
    if tech.missing_audio:
        issues.append(
            QaIssueSpec(
                code="MISSING_AUDIO",
                severity="high",
                category="technical",
                message="missing audio stream",
                recommended_action="regenerate",
            )
        )
    if not tech.av_sync_ok and not tech.missing_audio:
        issues.append(
            QaIssueSpec(
                code="AV_SYNC_FAILURE",
                severity="high",
                category="technical",
                message="A/V sync check failed",
                recommended_action="regenerate",
            )
        )

    # Aspect ratio
    w = int(probed.get("width") or expected_w)
    h = int(probed.get("height") or expected_h)
    aspect_ok = abs((w / h) - (9 / 16)) < 0.02 if h else False
    _m("aspect_ratio", round(w / h, 4) if h else None, round(9 / 16, 4), aspect_ok)
    if not aspect_ok:
        issues.append(
            QaIssueSpec(
                code="ASPECT_RATIO_MISMATCH",
                severity="high",
                category="technical",
                message=f"expected ~9:16 got {w}x{h}",
                recommended_action="repair",
            )
        )

    # Stub black/frozen markers from prior or injected
    if prior.get("black_frame_risk"):
        issues.append(
            QaIssueSpec(
                code="BLACK_FRAME",
                severity="high",
                category="technical",
                message="unexpected black frames detected",
                recommended_action="regenerate",
            )
        )

    score = float(tech.technical_score or 0)
    if prior.get("technical_score") and tech.ok:
        score = max(score, float(prior["technical_score"]))
    passed = tech.ok and aspect_ok and not any(i.severity == "critical" for i in issues)
    return DimensionResult(
        dimension="technical",
        score=round(score, 4),
        passed=passed,
        issues=issues,
        measurements=measurements,
        notes=list(tech.notes or []),
    )
