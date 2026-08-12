from __future__ import annotations

from typing import Any

from music_sfx_engine.schemas import (
    AudioBlueprint,
    EmotionalPoint,
    EnergyPoint,
    MusicMood,
    MusicSpecification,
    SilenceSpec,
    SfxSpec,
)


def build_audio_blueprint(
    *,
    storyboard_doc: dict[str, Any] | None = None,
    story_blueprint: dict[str, Any] | None = None,
    total_duration_sec: float | None = None,
    character_audio: dict[str, Any] | None = None,
    world_audio: dict[str, Any] | None = None,
) -> AudioBlueprint:
    """Story + Storyboard → AudioBlueprint (creative intent; not provider syntax)."""
    board = storyboard_doc or {}
    story = story_blueprint or {}
    scenes = board.get("scenes") or []
    duration = float(
        total_duration_sec
        or board.get("total_duration_sec")
        or story.get("target_duration_sec")
        or _scenes_duration(scenes)
        or 30
    )

    emotional_arc = _emotional_arc_from_scenes(scenes, story, duration)
    story_beats = _story_beats(scenes, story)
    sfx_items = _sfx_from_storyboard(board, scenes, duration)
    silences = _silences_from_board(board, scenes)
    voice_windows = _voice_windows(scenes)

    music_mood = _infer_mood(emotional_arc, board, story)
    genre = "cinematic_horror"
    cues = board.get("music_cues") or []
    if cues and isinstance(cues[0], dict) and cues[0].get("genre"):
        genre = str(cues[0]["genre"])
    elif (story.get("creative_direction") or {}).get("music_genre"):
        genre = str((story.get("creative_direction") or {}).get("music_genre"))
    elif "horror" in str((story.get("creative_direction") or {}).get("visual_style") or ""):
        genre = "cinematic_horror"

    tempo = float((character_audio or {}).get("tempo") or 82)
    instruments = list(
        (character_audio or {}).get("instruments")
        or ["low_strings", "sub_bass", "atmospheric_pad", "percussion"]
    )

    energy_curve = [
        EnergyPoint(time=p.time, intensity=round(p.intensity, 3)) for p in emotional_arc
    ]
    segments = _music_segments(emotional_arc, duration, silences)

    music_spec = MusicSpecification(
        purpose="background_score",
        mood=MusicMood(primary=music_mood, secondary="mysterious"),
        genre=genre,
        tempo_bpm=tempo,
        instrumentation=instruments,
        vocals_enabled=False,
        energy_curve=energy_curve,
        duration_sec=duration,
        segments=segments,
        character_theme=dict(character_audio or {}),
        world_theme=dict(world_audio or {}),
    )

    return AudioBlueprint(
        total_duration_sec=duration,
        emotional_arc=emotional_arc,
        music={"required": True, "purpose": "background_score"},
        ambience={
            "required": True,
            "profile": (world_audio or {}).get("ambient_profile") or ["location_ambience"],
        },
        sfx={"required": bool(sfx_items), "items": [s.model_dump() for s in sfx_items]},
        silences=silences,
        voice_windows=voice_windows,
        story_beats=story_beats,
        music_spec=music_spec,
        lineage={
            "storyboard_id": board.get("id"),
            "story_id": story.get("id") or board.get("story_id"),
        },
    )


def _scene_start(sc: dict[str, Any]) -> float:
    return float(sc.get("start_time_sec") or sc.get("start_sec") or sc.get("start") or 0)


def _scene_end(sc: dict[str, Any]) -> float:
    return float(sc.get("end_time_sec") or sc.get("end_sec") or sc.get("end") or 0)


def _shot_start(sh: dict[str, Any], sc: dict[str, Any]) -> float:
    return float(
        sh.get("start_time_sec") or sh.get("start_sec") or _scene_start(sc)
    )


def _scenes_duration(scenes: list[dict[str, Any]]) -> float:
    if not scenes:
        return 0.0
    ends = [_scene_end(s) for s in scenes]
    return max(ends) if ends else 0.0


def _emotional_arc_from_scenes(
    scenes: list[dict[str, Any]], story: dict[str, Any], duration: float
) -> list[EmotionalPoint]:
    points: list[EmotionalPoint] = []
    tension = story.get("tension_curve") or []
    if scenes:
        for sc in scenes:
            t = _scene_start(sc)
            emo_state = sc.get("emotional_state") or {}
            emo = str(
                emo_state.get("end")
                or emo_state.get("start")
                or sc.get("emotion")
                or sc.get("narrative_function")
                or "curiosity"
            )
            ten = sc.get("tension") or {}
            if isinstance(ten, dict):
                intensity = float(ten.get("end") if ten.get("end") is not None else ten.get("start") or 0.4)
            else:
                intensity = float(ten or sc.get("intensity") or 0.4)
            fn = str(sc.get("narrative_function") or sc.get("function") or "")
            defaults = {
                "hook": 0.25,
                "setup": 0.35,
                "conflict": 0.55,
                "escalation": 0.7,
                "twist": 0.95,
                "ending": 0.45,
                "cta": 0.35,
            }
            if fn in defaults and not (isinstance(ten, dict) and ten.get("end") is not None):
                intensity = defaults[fn]
            if fn == "twist":
                emo = "shock"
            points.append(EmotionalPoint(time=t, emotion=emo, intensity=float(intensity)))
    elif tension:
        for pt in tension:
            if isinstance(pt, dict):
                points.append(
                    EmotionalPoint(
                        time=float(pt.get("time") or pt.get("t") or 0),
                        emotion=str(pt.get("emotion") or "tension"),
                        intensity=float(pt.get("intensity") or pt.get("value") or 0.5),
                    )
                )
    if not points:
        points = [
            EmotionalPoint(time=0, emotion="curiosity", intensity=0.25),
            EmotionalPoint(time=duration * 0.4, emotion="tension", intensity=0.55),
            EmotionalPoint(time=duration * 0.55, emotion="fear", intensity=0.85),
            EmotionalPoint(time=duration * 0.6, emotion="shock", intensity=1.0),
            EmotionalPoint(time=duration * 0.85, emotion="relief", intensity=0.4),
        ]
    return points


def _story_beats(scenes: list[dict[str, Any]], story: dict[str, Any]) -> list[dict[str, Any]]:
    beats = []
    for sc in scenes:
        beats.append(
            {
                "function": sc.get("narrative_function") or sc.get("function"),
                "start": _scene_start(sc),
                "end": _scene_end(sc),
                "emotion": (sc.get("emotional_state") or {}).get("end"),
            }
        )
    if beats:
        return beats
    for name in ("hook", "conflict", "escalation", "twist", "ending", "cta"):
        block = story.get(name)
        if isinstance(block, dict):
            beats.append(
                {"function": name, **{k: block.get(k) for k in ("duration_sec", "emotion")}}
            )
    return beats


def _sfx_from_storyboard(
    board: dict[str, Any], scenes: list[dict[str, Any]], duration: float
) -> list[SfxSpec]:
    items: list[SfxSpec] = []
    n = 0
    for sc in scenes:
        for sh in sc.get("shots") or []:
            audio = sh.get("audio") or {}
            shot_start = _shot_start(sh, sc)
            for raw in list(audio.get("sfx") or []) + list(sc.get("sound_effects") or []):
                n += 1
                if isinstance(raw, str):
                    items.append(SfxSpec(id=f"sfx_{n:03d}", type=raw, start_sec=shot_start))
                elif isinstance(raw, dict):
                    timing = float(raw.get("timing") or 0)
                    items.append(
                        SfxSpec(
                            id=str(raw.get("id") or f"sfx_{n:03d}"),
                            type=str(raw.get("type") or raw.get("name") or "impact"),
                            start_sec=float(raw.get("start_sec") or shot_start + timing),
                            duration_sec=float(raw.get("duration_sec") or 1.0),
                            intensity=float(raw.get("intensity") or 0.7),
                            tags=list(raw.get("tags") or []),
                            visual_event=raw.get("visual_event") or raw.get("purpose"),
                        )
                    )
    if not items and duration >= 10:
        twist_t = duration * 0.5
        for sc in scenes:
            if (sc.get("narrative_function") or sc.get("function")) == "twist":
                twist_t = _scene_start(sc) or twist_t
                break
        items = [
            SfxSpec(id="sfx_001", type="footsteps", start_sec=max(2.0, duration * 0.1), duration_sec=0.4, intensity=0.5, tags=["horror"]),
            SfxSpec(id="sfx_002", type="footsteps", start_sec=max(3.5, duration * 0.15), duration_sec=0.4, intensity=0.55, tags=["horror"]),
            SfxSpec(id="sfx_003", type="door_creak", start_sec=max(8.0, twist_t - 2.5), duration_sec=1.2, intensity=0.7, tags=["horror", "wood"], visual_event="door_opens"),
            SfxSpec(id="sfx_004", type="impact", start_sec=twist_t + 0.4, duration_sec=0.5, intensity=1.0, tags=["horror", "hit"], visual_event="twist_reveal"),
            SfxSpec(id="sfx_005", type="whoosh", start_sec=max(1.0, duration * 0.05), duration_sec=0.35, intensity=0.45, tags=["transition"]),
            SfxSpec(id="sfx_006", type="stinger", start_sec=max(duration - 3.5, duration * 0.88), duration_sec=0.8, intensity=0.8, tags=["cta"], visual_event="cta"),
        ]
    return items


def _silences_from_board(
    board: dict[str, Any], scenes: list[dict[str, Any]]
) -> list[SilenceSpec]:
    silences: list[SilenceSpec] = []
    for sc in scenes:
        for sh in sc.get("shots") or []:
            audio = sh.get("audio") or {}
            shot_start = _shot_start(sh, sc)
            sil = audio.get("silence")
            if isinstance(sil, dict) and sil.get("duration_sec"):
                dur = float(sil["duration_sec"])
                silences.append(
                    SilenceSpec(
                        start_sec=shot_start,
                        end_sec=round(shot_start + dur, 3),
                        reason="shot_silence",
                    )
                )
            music = audio.get("music") or {}
            if music.get("action") == "stop":
                silences.append(
                    SilenceSpec(
                        start_sec=shot_start,
                        end_sec=round(shot_start + 0.4, 3),
                        reason="twist",
                    )
                )
    for pi in board.get("pattern_interrupts") or []:
        if pi.get("type") in {"audio_cut", "music_stop"}:
            t = float(pi.get("time_sec") or 0)
            silences.append(
                SilenceSpec(start_sec=t, end_sec=round(t + 0.4, 3), reason="pattern_interrupt")
            )
    silences.sort(key=lambda s: s.start_sec)
    return silences


def _voice_windows(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    windows = []
    for sc in scenes:
        for sh in sc.get("shots") or []:
            audio = sh.get("audio") or {}
            narr = audio.get("narration") or sc.get("narration")
            if isinstance(narr, dict) and narr.get("text"):
                start = _shot_start(sh, sc)
                dur = float(narr.get("estimated_duration_sec") or 2.0)
                windows.append({"start": start, "end": round(start + dur, 3), "kind": "narration"})
    return windows


def _infer_mood(
    arc: list[EmotionalPoint], board: dict[str, Any], story: dict[str, Any]
) -> str:
    if arc:
        peak = max(arc, key=lambda p: p.intensity)
        mapping = {
            "fear": "ominous",
            "shock": "ominous",
            "tension": "tense",
            "curiosity": "mysterious",
            "relief": "warm",
            "joy": "playful",
        }
        return mapping.get(peak.emotion, "ominous")
    style = (story.get("creative_direction") or {}).get("visual_style") or ""
    if "horror" in str(style):
        return "ominous"
    return "neutral"


def _music_segments(
    arc: list[EmotionalPoint], duration: float, silences: list[SilenceSpec]
) -> list[dict[str, Any]]:
    labels = ["intro", "build", "peak", "drop", "resolution", "outro"]
    if not arc:
        step = duration / len(labels)
        return [
            {"name": labels[i], "start": round(i * step, 3), "end": round((i + 1) * step, 3)}
            for i in range(len(labels))
        ]
    segs = []
    times = sorted({0.0, duration, *[p.time for p in arc]})
    for i in range(len(times) - 1):
        name = labels[min(i, len(labels) - 1)]
        segs.append({"name": name, "start": times[i], "end": times[i + 1]})
    for sil in silences:
        segs.append({"name": "silence", "start": sil.start_sec, "end": sil.end_sec})
    return segs
