from __future__ import annotations

from qa_engine.schemas import DimensionResult, QaIssueSpec, QaMeasurementSpec, QaPackage, QaThresholds


def run_audio_qa(package: QaPackage, thresholds: QaThresholds) -> DimensionResult:
    issues: list[QaIssueSpec] = []
    measurements: list[QaMeasurementSpec] = []
    score = 0.9

    voice = package.voice_clips or (package.specification or {}).get("voice_clips") or []
    music = package.music_clips or (package.specification or {}).get("music_clips") or []
    sfx = package.sfx_clips or (package.specification or {}).get("sfx_clips") or []
    ducking = (package.specification or {}).get("ducking") or {}

    measurements.append(
        QaMeasurementSpec(
            dimension="audio",
            metric="voice_present",
            value=1.0 if voice else 0.0,
            threshold=0.0,
            passed=True,
        )
    )
    measurements.append(
        QaMeasurementSpec(
            dimension="audio",
            metric="music_present",
            value=1.0 if music else 0.0,
            threshold=0.0,
            passed=True,
        )
    )

    # Ducking: if voice + music, bed should be quieter than target duck
    if voice and music:
        bed = float(ducking.get("bed_db") or music[0].get("volume_db") or -12)
        target = float(ducking.get("target_db") or -20)
        duck_ok = target <= bed
        measurements.append(
            QaMeasurementSpec(
                dimension="audio",
                metric="ducking_configured",
                value=target,
                threshold=bed,
                passed=duck_ok,
            )
        )
        if not duck_ok:
            issues.append(
                QaIssueSpec(
                    code="DUCKING_FAILURE",
                    severity="medium",
                    category="audio",
                    message="music bed not quieter than duck target while voice present",
                    recommended_action="repair",
                )
            )
            score = min(score, 0.75)

    for m in music:
        vol = float(m.get("volume_db") or 0)
        if vol > -3:
            issues.append(
                QaIssueSpec(
                    code="MUSIC_TOO_LOUD",
                    severity="medium",
                    category="audio",
                    message=f"music volume_db={vol} too high",
                    artifact_id=m.get("artifact_id"),
                    recommended_action="repair",
                )
            )
            score = min(score, 0.72)

    # Emotional fit heuristic: story emotion vs music metadata
    story_emotion = (
        ((package.story or {}).get("emotion") or "")
        or ((package.storyboard or {}).get("emotion") or "")
        or ""
    ).lower()
    for m in music:
        mood = str((m.get("metadata") or {}).get("mood") or (m.get("metadata") or {}).get("emotion") or "").lower()
        if story_emotion in {"fear", "horror", "suspense"} and mood in {"happy", "upbeat", "comedy"}:
            issues.append(
                QaIssueSpec(
                    code="MUSIC_EMOTIONAL_MISMATCH",
                    severity="high",
                    category="audio",
                    message=f"story emotion={story_emotion} music mood={mood}",
                    artifact_id=m.get("artifact_id"),
                    recommended_action="regenerate",
                )
            )
            score = min(score, 0.55)

    # SFX timing vs declared start
    for s in sfx:
        start = float(s.get("start") or 0)
        end = float(s.get("end") or start)
        if end < start:
            issues.append(
                QaIssueSpec(
                    code="SFX_SYNC_FAILURE",
                    severity="medium",
                    category="audio",
                    message="sfx end before start",
                    artifact_id=s.get("artifact_id"),
                    timestamp_sec=start,
                    recommended_action="repair",
                )
            )
            score = min(score, 0.7)

    for inj in package.injected_issues:
        if inj.category == "audio" or inj.code.startswith(("MUSIC_", "SFX_", "VOICE_", "DUCKING_", "DIALOGUE_")):
            issues.append(inj)
            if inj.score is not None:
                score = min(score, float(inj.score))

    return DimensionResult(
        dimension="audio",
        score=round(score, 4),
        passed=score >= 0.7,
        issues=issues,
        measurements=measurements,
    )
