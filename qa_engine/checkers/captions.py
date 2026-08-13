from __future__ import annotations

from assembly_engine.profiles import get_platform_profile
from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_caption_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    score = 0.96
    captions = package.captions or (package.specification or {}).get("captions") or []
    voice = package.voice_clips or (package.specification or {}).get("voice_clips") or []
    enabled = bool((package.specification or {}).get("captions_enabled", True))

    if enabled and voice and not captions:
        issues.append(
            QaIssueSpec(
                code="CAPTION_MISMATCH",
                severity="medium",
                category="captions",
                message="captions enabled but caption timeline empty while voice present",
                recommended_action="repair",
            )
        )
        score = 0.6

    # Transcript check against expected script / voice text
    expected = (package.expected_script or "").strip().lower()
    if not expected and voice:
        expected = str((voice[0].get("metadata") or {}).get("text") or "").strip().lower()
    if captions and expected:
        joined = " ".join(str(c.get("text") or "") for c in captions).lower()
        # Normalize punctuation lightly
        exp_norm = expected.replace(".", "").replace("!", "").replace("?", "")
        got_norm = joined.replace(".", "").replace("!", "").replace("?", "")
        # Allow partial containment
        ok = exp_norm in got_norm or got_norm in exp_norm or _token_overlap(exp_norm, got_norm) >= 0.7
        measurements.append(
            QaMeasurementSpec(
                dimension="captions",
                metric="transcript_match",
                value=1.0 if ok else 0.0,
                threshold=1.0,
                passed=ok,
            )
        )
        if not ok:
            issues.append(
                QaIssueSpec(
                    code="CAPTION_MISMATCH",
                    severity="medium",
                    category="captions",
                    message="caption text diverges from expected script",
                    recommended_action="repair",
                )
            )
            score = min(score, 0.65)

    # Timing vs voice
    tol = thresholds.caption_timing_tolerance_ms / 1000.0
    if captions and voice:
        v0 = voice[0]
        c0 = captions[0]
        drift = abs(float(c0.get("start") or 0) - float(v0.get("start") or 0))
        ok = drift <= tol + 0.05
        measurements.append(
            QaMeasurementSpec(
                dimension="captions",
                metric="timing_drift_sec",
                value=drift,
                threshold=tol,
                passed=ok,
            )
        )
        if not ok:
            issues.append(
                QaIssueSpec(
                    code="CAPTION_TIMING",
                    severity="medium",
                    category="captions",
                    message=f"caption timing drift {drift:.3f}s",
                    timestamp_sec=float(c0.get("start") or 0),
                    recommended_action="repair",
                )
            )
            score = min(score, 0.7)

    # Safe zone — position bottom_safe is OK; absolute y too low fails
    try:
        profile = get_platform_profile(package.platform_profile)
        safe = profile.get("safe_zone") or {}
        bottom = int(safe.get("bottom") or 300)
        height = int(package.height or profile["canvas"].height)
    except Exception:  # noqa: BLE001
        bottom, height = 300, 1920
    for c in captions:
        pos = c.get("position")
        if isinstance(pos, dict) and "y" in pos:
            y = float(pos["y"])
            # y as normalized 0-1; bottom safe roughly below 1 - bottom/height
            limit = 1.0 - (bottom / max(height, 1)) + 0.02
            if y > limit + 0.05:
                issues.append(
                    QaIssueSpec(
                        code="CAPTION_SAFE_ZONE",
                        severity="medium",
                        category="captions",
                        message=f"caption y={y} outside bottom safe zone",
                        recommended_action="repair",
                    )
                )
                score = min(score, 0.68)
        elif pos not in {None, "bottom_safe", "center", "top_safe"}:
            pass

    for inj in package.injected_issues:
        if inj.category == "captions" or inj.code.startswith("CAPTION_"):
            issues.append(inj)

    return DimensionResult(
        dimension="captions",
        score=round(score, 4),
        passed=score >= 0.7,
        issues=issues,
        measurements=measurements,
    )


def _token_overlap(a: str, b: str) -> float:
    ta = {t for t in a.split() if t}
    tb = {t for t in b.split() if t}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
