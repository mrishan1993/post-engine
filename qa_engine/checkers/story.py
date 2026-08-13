from __future__ import annotations

from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_story_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    story = package.story or {}
    board = package.storyboard or {}
    overlays = package.overlays or (package.specification or {}).get("overlays") or []
    duration = float(package.duration_sec or (package.specification or {}).get("duration_sec") or 30)

    beats = {
        "hook": 0.9,
        "conflict": 0.88,
        "escalation": 0.9,
        "twist": 0.85,
        "ending": 0.87,
        "cta": 0.5,
    }
    # Presence signals from storyboard narrative functions / overlays
    funcs = {
        str(sc.get("narrative_function") or (sc.get("metadata") or {}).get("narrative_function") or "").lower()
        for sc in (board.get("scenes") or (package.specification or {}).get("scenes") or [])
    }
    for key in list(beats):
        if key in funcs or any(key in f for f in funcs):
            beats[key] = max(beats[key], 0.92)

    cta_overlays = [o for o in overlays if str(o.get("role") or "").lower() == "cta"]
    if cta_overlays:
        beats["cta"] = 0.95
        cta = cta_overlays[0]
        start = float(cta.get("start") or 0)
        if start < duration - 6:
            issues.append(
                QaIssueSpec(
                    code="CTA_TIMING",
                    severity="medium",
                    category="story",
                    message=f"CTA starts at {start}s; expected near end (~{duration-3.5:.1f}s)",
                    timestamp_sec=start,
                    recommended_action="repair",
                )
            )
            beats["cta"] = 0.7
    else:
        issues.append(
            QaIssueSpec(
                code="CTA_TIMING",
                severity="low",
                category="story",
                message="CTA overlay missing",
                recommended_action="repair",
            )
        )

    for k, v in beats.items():
        measurements.append(
            QaMeasurementSpec(dimension="story", metric=k, value=v, threshold=0.7, passed=v >= 0.7)
        )

    # Fidelity: optional expected action vs metadata
    expected_action = (story.get("key_action") or "").lower()
    actual_action = (board.get("key_action") or story.get("realized_action") or expected_action).lower()
    if expected_action and actual_action and expected_action != actual_action:
        issues.append(
            QaIssueSpec(
                code="STORY_FIDELITY_FAILURE",
                severity="high",
                category="story",
                message=f"expected action '{expected_action}' vs '{actual_action}'",
                recommended_action="regenerate",
            )
        )
        beats["conflict"] = min(beats["conflict"], 0.5)

    for inj in package.injected_issues:
        if inj.category == "story" or inj.code.startswith("STORY_"):
            issues.append(inj)

    score = sum(beats.values()) / len(beats)
    return DimensionResult(
        dimension="story",
        score=round(score, 4),
        passed=score >= 0.7,
        issues=issues,
        measurements=measurements,
    )
