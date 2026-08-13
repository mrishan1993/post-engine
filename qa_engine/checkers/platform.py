from __future__ import annotations

from pathlib import Path

from publishing_engine.profiles import get_platform_profile
from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_platform_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    score = 1.0
    platforms = package.target_platforms or ["instagram"]
    dur = float(package.duration_sec or (package.specification or {}).get("duration_sec") or 0)
    size_mb = 0.0
    if package.storage_uri and Path(package.storage_uri).exists():
        size_mb = Path(package.storage_uri).stat().st_size / (1024 * 1024)

    for platform in platforms:
        try:
            profile = get_platform_profile(platform)
        except ValueError:
            issues.append(
                QaIssueSpec(
                    code="PLATFORM_CONSTRAINT",
                    severity="high",
                    category="platform",
                    message=f"unknown platform profile: {platform}",
                    recommended_action="block",
                )
            )
            score = min(score, 0.4)
            continue
        min_d = float(profile.get("min_duration_sec") or 0)
        max_d = float(profile.get("max_duration_sec") or 9999)
        max_mb = float(profile.get("max_file_size_mb") or 500)
        dur_ok = min_d <= dur <= max_d if dur else True
        size_ok = size_mb <= max_mb
        measurements.append(
            QaMeasurementSpec(
                dimension="platform",
                metric=f"{platform}_duration_ok",
                value=dur,
                threshold=max_d,
                passed=dur_ok,
            )
        )
        measurements.append(
            QaMeasurementSpec(
                dimension="platform",
                metric=f"{platform}_size_ok",
                value=size_mb,
                threshold=max_mb,
                passed=size_ok,
            )
        )
        if not dur_ok:
            issues.append(
                QaIssueSpec(
                    code="PLATFORM_CONSTRAINT",
                    severity="high",
                    category="platform",
                    message=f"{platform}: duration {dur} outside [{min_d},{max_d}]",
                    recommended_action="repair",
                )
            )
            score = min(score, 0.5)
        if not size_ok:
            issues.append(
                QaIssueSpec(
                    code="PLATFORM_CONSTRAINT",
                    severity="high",
                    category="platform",
                    message=f"{platform}: file size {size_mb:.1f}MB exceeds {max_mb}",
                    recommended_action="repair",
                )
            )
            score = min(score, 0.5)

    return DimensionResult(
        dimension="platform",
        score=round(score, 4),
        passed=score >= 0.9,
        issues=issues,
        measurements=measurements,
    )
