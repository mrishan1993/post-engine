from __future__ import annotations

from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_character_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    score = 0.95

    scenes = (package.specification or {}).get("scenes") or (package.storyboard or {}).get("scenes") or []
    per_scene: list[float] = []
    for i, sc in enumerate(scenes):
        sid = str(sc.get("scene_id") or sc.get("id") or f"scene_{i+1}")
        # Deterministic baseline; injected issues can drop a scene
        sim = 0.94 - (i * 0.01)
        for inj in package.injected_issues:
            if inj.code == "CHARACTER_DRIFT" and (inj.scene_id == sid or inj.scene_id is None):
                sim = float(inj.score if inj.score is not None else 0.58)
                issues.append(inj if inj.scene_id else inj.model_copy(update={"scene_id": sid}))
        per_scene.append(sim)
        measurements.append(
            QaMeasurementSpec(
                dimension="character",
                metric="identity_similarity",
                value=sim,
                threshold=thresholds.character_min_score,
                passed=sim >= thresholds.character_min_score,
                metadata={"scene_id": sid},
            )
        )
        if sim < thresholds.character_min_score and not any(
            x.code == "CHARACTER_DRIFT" and x.scene_id == sid for x in issues
        ):
            issues.append(
                QaIssueSpec(
                    code="CHARACTER_DRIFT",
                    severity="high",
                    category="character",
                    scene_id=sid,
                    score=sim,
                    message=f"Character similarity {sim:.2f} below {thresholds.character_min_score}",
                    owner_engine="video_generation",
                    recommended_action="regenerate",
                )
            )

    if per_scene:
        score = sum(per_scene) / len(per_scene)
    elif package.character_slug:
        score = 0.92
        measurements.append(
            QaMeasurementSpec(
                dimension="character",
                metric="identity_similarity",
                value=score,
                threshold=thresholds.character_min_score,
                passed=True,
            )
        )

    # Canon rules
    canon = package.character_canon or {}
    forbidden = set(canon.get("forbidden_props") or [])
    story_props = set()
    for sc in scenes:
        for p in sc.get("props") or (sc.get("metadata") or {}).get("props") or []:
            story_props.add(str(p).lower())
    for prop in forbidden:
        if prop.lower() in story_props:
            issues.append(
                QaIssueSpec(
                    code="CANON_VIOLATION",
                    severity="high",
                    category="character",
                    message=f"Character canon forbids prop '{prop}'",
                    owner_engine="storyboard",
                    recommended_action="regenerate",
                )
            )
            score = min(score, 0.5)

    for inj in package.injected_issues:
        if inj.code == "CANON_VIOLATION" and inj not in issues:
            issues.append(inj)
            score = min(score, float(inj.score or 0.5))

    return DimensionResult(
        dimension="character",
        score=round(score, 4),
        passed=score >= thresholds.character_min_score,
        issues=issues,
        measurements=measurements,
    )
