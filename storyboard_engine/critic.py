from __future__ import annotations

from storyboard_engine.schemas import (
    StoryboardCriticResult,
    StoryboardDocument,
    StoryboardQuality,
    StoryboardRequest,
)


def evaluate_quality(
    doc: StoryboardDocument,
    request: StoryboardRequest,
    *,
    asset_availability: float = 1.0,
    continuity_flags: int = 0,
) -> StoryboardQuality:
    functions = {s.narrative_function for s in doc.scenes}
    needed = {"hook", "setup", "conflict", "ending"}
    coverage = len(needed & functions) / len(needed)

    # Timing: scenes contiguous and within platform max
    timing = 1.0
    cursor = 0.0
    for sc in doc.scenes:
        if abs(sc.start_time_sec - cursor) > 0.05:
            timing -= 0.1
        if sc.end_time_sec < sc.start_time_sec:
            timing -= 0.2
        cursor = sc.end_time_sec
        for sh in sc.shots:
            narr = (sh.audio.narration or {}) if sh.audio else {}
            est = float(narr.get("estimated_duration_sec") or 0)
            if est and est > sh.duration_sec + 0.5:
                timing -= 0.08
    platform_max = float((doc.global_direction.platform or {}).get("max_duration_sec") or 90)
    if doc.duration_sec > platform_max:
        timing -= 0.2
    timing = max(0.0, min(1.0, timing))

    char_cont = max(0.5, 1.0 - 0.08 * continuity_flags)
    loc_cont = 0.95 if all(s.location_name for s in doc.scenes) else 0.7
    prop_cont = 0.95 if doc.scenes and doc.scenes[0].prop_state is not None else 0.8

    # Camera: avoid wild angle flips every shot without pattern interrupt
    cam = 0.9
    angles = [sh.camera.angle for sc in doc.scenes for sh in sc.shots]
    if len(set(angles)) > max(4, len(angles) // 2):
        cam -= 0.1

    audio_sync = 0.9
    if any(sc.narration for sc in doc.scenes) or any(
        (sh.audio.narration for sc in doc.scenes for sh in sc.shots)
    ):
        audio_sync = 0.95
    if doc.music_cues:
        audio_sync = min(1.0, audio_sync + 0.02)

    platform_fit = 0.9 if doc.global_direction.aspect_ratio in {"9:16", "1:1"} else 0.7
    if request.platform == doc.platform:
        platform_fit = min(1.0, platform_fit + 0.05)

    pacing = 0.75
    if 1.5 <= doc.pacing.average_shot_duration_sec <= 4.0:
        pacing += 0.1
    if doc.pacing.cuts_per_10_sec >= 2:
        pacing += 0.05
    if doc.pattern_interrupts:
        pacing += 0.05
    pacing = min(0.99, pacing)

    retention = 0.7
    hook_scenes = [s for s in doc.scenes if s.narrative_function == "hook"]
    if hook_scenes and hook_scenes[0].shots:
        if any(sh.camera.movement != "static" for sh in hook_scenes[0].shots):
            retention += 0.1
        if hook_scenes[0].duration_sec <= 4.5:
            retention += 0.05
    if (request.predicted_retention or 1) < 0.6 and doc.pacing.motion_density >= 0.5:
        retention += 0.08
    retention = min(0.99, retention)

    scores = {
        "narrative_coverage": round(coverage, 4),
        "timing": round(timing, 4),
        "character_continuity": round(char_cont, 4),
        "location_continuity": round(loc_cont, 4),
        "prop_continuity": round(prop_cont, 4),
        "camera_continuity": round(cam, 4),
        "audio_sync": round(audio_sync, 4),
        "asset_availability": round(asset_availability, 4),
        "platform_compatibility": round(platform_fit, 4),
        "visual_pacing": round(pacing, 4),
        "retention_potential": round(retention, 4),
    }
    overall = sum(scores.values()) / len(scores)
    return StoryboardQuality(**scores, overall=round(overall, 4))


def critique_storyboard(
    doc: StoryboardDocument, request: StoryboardRequest
) -> StoryboardCriticResult:
    notes: list[str] = []
    fixes: list[str] = []

    functions = {s.narrative_function for s in doc.scenes}
    narrative_covered = {"hook", "ending"}.issubset(functions) and (
        "conflict" in functions or "escalation" in functions
    )
    if not narrative_covered:
        notes.append("Missing core narrative beats in visuals.")
        fixes.append("Ensure hook, conflict/escalation, and ending scenes exist.")

    hook_visual = False
    for sc in doc.scenes:
        if sc.narrative_function == "hook":
            hook_visual = bool(sc.shots) and (
                any(sh.camera.movement != "static" for sh in sc.shots)
                or any(sh.shot_type in {"pov", "close_up", "extreme_close_up"} for sh in sc.shots)
            )
            if sc.start_time_sec > 0.1:
                notes.append("Hook does not start at 0.")
            break
    if not hook_visual:
        fixes.append("Add POV/movement or close-up in first 3 seconds.")

    all_shots = [sh for sc in doc.scenes for sh in sc.shots]
    long_shots = [sh for sh in all_shots if sh.duration_sec > 5.5]
    shot_lengths_ok = len(long_shots) == 0
    if not shot_lengths_ok:
        fixes.append("Split shots longer than ~5.5s.")

    no_unnecessary = len(all_shots) <= max(14, len(doc.scenes) * 3)
    if not no_unnecessary:
        notes.append("Shot count may be high for duration.")

    enough_pattern = len(doc.pattern_interrupts) >= 1 or doc.pacing.motion_density >= 0.4
    if not enough_pattern:
        fixes.append("Add at least one pattern interrupt (audio cut / insert / black).")

    camera_consistent = True
    for sc in doc.scenes:
        dirs = [sh.camera.screen_direction for sh in sc.shots]
        if "left" in dirs and "right" in dirs and sc.narrative_function not in {"twist", "escalation"}:
            camera_consistent = False
            notes.append(f"Screen direction flips in {sc.narrative_function}.")
            break

    positions_logical = all(sc.location_name for sc in doc.scenes)
    audio_reinforces = bool(doc.music_cues) or any(
        sh.audio.sfx or sh.audio.silence for sc in doc.scenes for sh in sc.shots
    )
    twist_emphasized = True
    if any(sc.narrative_function == "twist" for sc in doc.scenes):
        twist_emphasized = any(
            sh.shot_type in {"insert", "extreme_close_up", "close_up"}
            for sc in doc.scenes
            if sc.narrative_function == "twist"
            for sh in sc.shots
        ) and any(pi.type == "audio_cut" for pi in doc.pattern_interrupts)
        if not twist_emphasized:
            fixes.append("Emphasize twist with insert/close-up + audio cut.")

    ending_lands = any(sc.narrative_function in {"ending", "cta"} for sc in doc.scenes)
    generation_realistic = all(
        sh.duration_sec <= 8 and sh.generation.modality in {"video", "image", "text_overlay", "audio"}
        for sh in all_shots
    )
    if not generation_realistic:
        fixes.append("Keep shot durations generation-friendly (<=8s).")

    flags = [
        narrative_covered,
        hook_visual,
        no_unnecessary,
        shot_lengths_ok,
        enough_pattern,
        camera_consistent,
        positions_logical,
        audio_reinforces,
        twist_emphasized,
        ending_lands,
        generation_realistic,
    ]
    score = sum(1 for f in flags if f) / len(flags)

    return StoryboardCriticResult(
        narrative_covered=narrative_covered,
        hook_visual_interest=hook_visual,
        no_unnecessary_shots=no_unnecessary,
        shot_lengths_ok=shot_lengths_ok,
        enough_pattern_changes=enough_pattern,
        camera_consistent=camera_consistent,
        positions_logical=positions_logical,
        audio_reinforces=audio_reinforces,
        twist_emphasized=twist_emphasized,
        ending_lands=ending_lands,
        generation_realistic=generation_realistic,
        notes=notes,
        suggested_fixes=fixes,
        critic_score=round(score, 4),
    )


def revise_storyboard(
    doc: StoryboardDocument, critic: StoryboardCriticResult, request: StoryboardRequest
) -> StoryboardDocument:
    data = doc.model_copy(deep=True)

    if not critic.shot_lengths_ok:
        for sc in data.scenes:
            new_shots = []
            for sh in sc.shots:
                if sh.duration_sec > 5.5:
                    mid = round(sh.start_time_sec + sh.duration_sec / 2, 3)
                    a = sh.model_copy(deep=True)
                    b = sh.model_copy(deep=True)
                    a.end_time_sec = mid
                    a.duration_sec = round(mid - a.start_time_sec, 3)
                    a.id = f"{sh.id}_a"
                    b.start_time_sec = mid
                    b.duration_sec = round(b.end_time_sec - mid, 3)
                    b.id = f"{sh.id}_b"
                    b.sequence = sh.sequence + 1
                    b.camera.movement = "handheld"
                    new_shots.extend([a, b])
                else:
                    new_shots.append(sh)
            for i, sh in enumerate(new_shots, 1):
                sh.sequence = i
            sc.shots = new_shots

    if not critic.enough_pattern_changes and data.scenes:
        # Insert silence interrupt near peak tension scene
        peak = max(data.scenes, key=lambda s: s.tension.get("end", 0))
        from storyboard_engine.schemas import PatternInterrupt

        data.pattern_interrupts.append(
            PatternInterrupt(
                time_sec=peak.start_time_sec + 0.5,
                type="music_stop",
                purpose="force pattern change",
            )
        )
        if peak.shots:
            peak.shots[0].audio.silence = {"duration_sec": 0.6}
            peak.shots[0].audio.music = {"action": "stop", "intensity": 0.0}

    if not critic.hook_visual_interest:
        for sc in data.scenes:
            if sc.narrative_function == "hook" and sc.shots:
                sc.shots[0].shot_type = "pov"
                sc.shots[0].camera.movement = "slow_push"
                break

    if not critic.twist_emphasized:
        for sc in data.scenes:
            if sc.narrative_function == "twist" and sc.shots:
                sc.shots[0].shot_type = "insert"
                sc.shots[0].audio.music = {"action": "stop", "intensity": 0.0}
                sc.shots[0].audio.silence = {"duration_sec": 0.8}
                from storyboard_engine.schemas import PatternInterrupt

                data.pattern_interrupts.append(
                    PatternInterrupt(
                        time_sec=sc.start_time_sec,
                        type="audio_cut",
                        purpose="emphasize twist",
                    )
                )
                break

    # Recompute pacing
    all_shots = [sh for sc in data.scenes for sh in sc.shots]
    if all_shots and data.scenes:
        data.duration_sec = round(data.scenes[-1].end_time_sec, 3)
        data.pacing.average_shot_duration_sec = round(
            sum(sh.duration_sec for sh in all_shots) / len(all_shots), 3
        )
        data.pacing.cuts_per_10_sec = round((len(all_shots) / max(data.duration_sec, 1)) * 10, 2)
        data.pacing.motion_density = round(
            sum(1 for sh in all_shots if sh.camera.movement != "static") / len(all_shots),
            2,
        )

    return data
