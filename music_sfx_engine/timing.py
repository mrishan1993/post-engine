from __future__ import annotations

from typing import Any

from music_sfx_engine.schemas import (
    AudioBlueprint,
    AudioTimeline,
    TimelineTrack,
)


def build_beat_grid(*, tempo_bpm: float, duration_sec: float) -> list[float]:
    if tempo_bpm <= 0:
        return []
    interval = 60.0 / tempo_bpm
    beats = []
    t = 0.0
    while t <= duration_sec + 1e-6:
        beats.append(round(t, 3))
        t += interval
    return beats


def build_audio_timeline(
    *,
    blueprint: AudioBlueprint,
    music_artifact_id: str | None,
    sfx_artifacts: list[dict[str, Any]],
    ambience_artifact_id: str | None = None,
    platform: str = "instagram_reels",
) -> AudioTimeline:
    """Compose Assembly-ready AudioTimeline from music + SFX + silence + ducking metadata."""
    duration = float(blueprint.total_duration_sec)
    tracks: list[TimelineTrack] = []
    music_spec = blueprint.music_spec
    bpm = float(music_spec.tempo_bpm) if music_spec else 82.0

    duck = {"music_bed_db": -12.0, "music_duck_db": -20.0}
    if music_artifact_id:
        # Split music around intentional silence windows
        silences = sorted(blueprint.silences, key=lambda s: s.start_sec)
        cursor = 0.0
        for sil in silences:
            if sil.start_sec > cursor:
                tracks.append(
                    TimelineTrack(
                        type="music",
                        artifact_id=music_artifact_id,
                        start=cursor,
                        end=sil.start_sec,
                        gain_db=duck["music_bed_db"],
                        fade_out_sec=0.05,
                    )
                )
            tracks.append(
                TimelineTrack(
                    type="silence",
                    artifact_id=None,
                    start=sil.start_sec,
                    end=sil.end_sec,
                    gain_db=-90,
                    metadata={"reason": sil.reason},
                )
            )
            cursor = sil.end_sec
        if cursor < duration:
            tracks.append(
                TimelineTrack(
                    type="music",
                    artifact_id=music_artifact_id,
                    start=cursor,
                    end=duration,
                    gain_db=duck["music_bed_db"],
                    fade_in_sec=0.05 if silences else 0.0,
                )
            )

    if blueprint.ambience.get("required"):
        tracks.append(
            TimelineTrack(
                type="ambience",
                artifact_id=ambience_artifact_id,
                start=0.0,
                end=duration,
                gain_db=-18.0,
                metadata={"profile": blueprint.ambience.get("profile")},
            )
        )

    for art in sfx_artifacts:
        meta = art.get("metadata") or art.get("metadata_json") or {}
        start = float(meta.get("start_sec") or art.get("start_sec") or 0)
        dur = float(art.get("duration_sec") or meta.get("duration_sec") or 1.0)
        intensity = float(meta.get("intensity") or 0.7)
        gain = -6.0 + intensity * 6.0
        tracks.append(
            TimelineTrack(
                type="sfx",
                artifact_id=art.get("id"),
                start=start,
                end=round(start + dur, 3),
                gain_db=round(gain, 2),
                sfx_type=meta.get("type"),
                metadata={
                    "visual_event": meta.get("visual_event"),
                    "source": meta.get("source"),
                },
            )
        )

    for vw in blueprint.voice_windows:
        tracks.append(
            TimelineTrack(
                type="voice",
                artifact_id=None,  # Voice Engine fills later
                start=float(vw.get("start") or 0),
                end=float(vw.get("end") or 0),
                gain_db=0.0,
                metadata={"kind": vw.get("kind"), "placeholder": True},
            )
        )

    tracks.sort(key=lambda t: (t.start, t.type))
    profile = {
        "instagram_reels": {"target_lufs": -14, "true_peak_db": -1},
        "youtube": {"target_lufs": -14, "true_peak_db": -1},
        "tiktok": {"target_lufs": -12, "true_peak_db": -1},
    }.get(platform, {"target_lufs": -14, "true_peak_db": -1})

    return AudioTimeline(
        duration_sec=duration,
        tracks=tracks,
        beat_grid=build_beat_grid(tempo_bpm=bpm, duration_sec=duration),
        voice_windows=list(blueprint.voice_windows),
        ducking={
            **duck,
            "windows": [
                {
                    "start": vw.get("start"),
                    "end": vw.get("end"),
                    "music_gain_db": duck["music_duck_db"],
                }
                for vw in blueprint.voice_windows
            ],
        },
        loudness_profile={"platform": platform, **profile},
    )
