from __future__ import annotations

from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_storyboard_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    scenes_spec = (package.specification or {}).get("scenes") or []
    scenes_board = (package.storyboard or {}).get("scenes") or []
    score = 0.92

    # Scene boundary alignment
    if scenes_board and scenes_spec:
        matched = 0
        for i, sc in enumerate(scenes_board):
            b_start = float(sc.get("start_time_sec") or sc.get("start") or 0)
            b_end = float(sc.get("end_time_sec") or sc.get("end") or 0)
            if i < len(scenes_spec):
                a = scenes_spec[i]
                a_start = float(a.get("start") or 0)
                a_end = float(a.get("end") or 0)
                ok = abs(a_start - b_start) <= 0.15 and abs(a_end - b_end) <= 0.15
                measurements.append(
                    QaMeasurementSpec(
                        dimension="storyboard",
                        metric="scene_boundary",
                        value=1.0 if ok else 0.0,
                        threshold=1.0,
                        passed=ok,
                        metadata={"scene_id": a.get("scene_id") or sc.get("id")},
                    )
                )
                if ok:
                    matched += 1
                else:
                    issues.append(
                        QaIssueSpec(
                            code="STORYBOARD_MISMATCH",
                            severity="medium",
                            category="storyboard",
                            scene_id=str(a.get("scene_id") or sc.get("id") or i),
                            message=f"scene boundary mismatch board={b_start}-{b_end} assembly={a_start}-{a_end}",
                            recommended_action="repair",
                        )
                    )
        score = matched / max(len(scenes_board), 1)
        score = 0.7 + 0.3 * score
    elif not scenes_spec and not scenes_board:
        score = 0.85
        measurements.append(
            QaMeasurementSpec(
                dimension="storyboard",
                metric="scenes_present",
                value=0.0,
                threshold=0.0,
                passed=True,
                metadata={"note": "no scenes to compare"},
            )
        )

    for inj in package.injected_issues:
        if inj.category == "storyboard" or inj.code == "STORYBOARD_MISMATCH":
            issues.append(inj)
            if inj.score is not None:
                score = min(score, float(inj.score))

    return DimensionResult(
        dimension="storyboard",
        score=round(score, 4),
        passed=score >= 0.7,
        issues=issues,
        measurements=measurements,
    )
