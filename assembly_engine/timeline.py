from __future__ import annotations

from typing import Any

from assembly_engine.schemas import (
    AssemblySpecification,
    BuiltTimeline,
    CaptionClipSpec,
    TimelineTrack,
)


def build_timeline(spec: AssemblySpecification) -> BuiltTimeline:
    """Deterministic track composition from AssemblySpecification."""
    tracks: list[TimelineTrack] = []

    if spec.video_clips:
        tracks.append(
            TimelineTrack(
                type="video",
                id="video_track_1",
                clips=[c.model_dump() for c in sorted(spec.video_clips, key=lambda x: x.start)],
            )
        )
    if spec.image_clips:
        tracks.append(
            TimelineTrack(
                type="image",
                id="image_track_1",
                clips=[c.model_dump() for c in sorted(spec.image_clips, key=lambda x: x.start)],
            )
        )
    if spec.voice_clips:
        tracks.append(
            TimelineTrack(
                type="voice",
                id="voice_track_1",
                clips=[c.model_dump() for c in sorted(spec.voice_clips, key=lambda x: x.start)],
            )
        )
    if spec.music_clips:
        tracks.append(
            TimelineTrack(
                type="music",
                id="music_track_1",
                clips=[c.model_dump() for c in sorted(spec.music_clips, key=lambda x: x.start)],
            )
        )
    if spec.sfx_clips:
        tracks.append(
            TimelineTrack(
                type="sfx",
                id="sfx_track_1",
                clips=[c.model_dump() for c in sorted(spec.sfx_clips, key=lambda x: x.start)],
            )
        )
    if spec.ambience_clips:
        tracks.append(
            TimelineTrack(
                type="ambience",
                id="ambience_track_1",
                clips=[c.model_dump() for c in sorted(spec.ambience_clips, key=lambda x: x.start)],
            )
        )
    if spec.captions_enabled and spec.captions:
        tracks.append(
            TimelineTrack(
                type="caption",
                id="caption_track_1",
                clips=[c.model_dump() for c in sorted(spec.captions, key=lambda x: x.start)],
            )
        )
    if spec.overlays:
        tracks.append(
            TimelineTrack(
                type="overlay",
                id="overlay_track_1",
                clips=[c.model_dump() for c in sorted(spec.overlays, key=lambda x: x.start)],
            )
        )
    if spec.effects_enabled and spec.effects:
        tracks.append(
            TimelineTrack(
                type="effect",
                id="effect_track_1",
                clips=[c.model_dump() for c in sorted(spec.effects, key=lambda x: x.start)],
            )
        )

    duration = float(spec.duration_sec)
    # Extend duration if clips run longer
    for track in tracks:
        for clip in track.clips:
            end = float(clip.get("end") or 0)
            if end > duration:
                duration = end

    if spec.cut_on_beat and spec.beat_grid:
        _align_video_cuts_to_beats(tracks, spec.beat_grid)

    return BuiltTimeline(
        duration_sec=round(duration, 3),
        canvas=spec.canvas,
        tracks=tracks,
        ducking=spec.ducking,
        silences=list(spec.silences),
    )


def _align_video_cuts_to_beats(tracks: list[TimelineTrack], beats: list[float]) -> None:
    if not beats:
        return
    for track in tracks:
        if track.type != "video":
            continue
        for clip in track.clips:
            start = float(clip.get("start") or 0)
            nearest = min(beats, key=lambda b: abs(b - start))
            if abs(nearest - start) <= 0.12:
                clip["start"] = round(nearest, 3)
                clip["metadata"] = {**(clip.get("metadata") or {}), "beat_aligned": True}


def captions_from_voice_timestamps(
    voice_clips: list[dict[str, Any]],
    *,
    style: str = "bold",
) -> list[CaptionClipSpec]:
    """Build caption timeline from voice word timestamps (Caption Engine input, not design)."""
    captions: list[CaptionClipSpec] = []
    for clip in voice_clips:
        words = ((clip.get("metadata") or {}).get("timestamps") or {}).get("words") or []
        offset = float(clip.get("start") or 0)
        if not words:
            text = (clip.get("metadata") or {}).get("text") or ""
            if text:
                captions.append(
                    CaptionClipSpec(
                        text=text.upper(),
                        start=offset,
                        end=float(clip.get("end") or offset + 1),
                        style=style,
                    )
                )
            continue
        # Group into short phrases (~4 words)
        chunk: list[dict[str, Any]] = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= 4 or w is words[-1]:
                start = offset + float(chunk[0].get("start") or 0)
                end = offset + float(chunk[-1].get("end") or start + 0.4)
                text = " ".join(str(x.get("word") or "") for x in chunk).upper()
                captions.append(
                    CaptionClipSpec(
                        text=text,
                        start=round(start, 3),
                        end=round(end, 3),
                        style=style,
                        words=[
                            {
                                "word": x.get("word"),
                                "start": round(offset + float(x.get("start") or 0), 3),
                                "end": round(offset + float(x.get("end") or 0), 3),
                            }
                            for x in chunk
                        ],
                    )
                )
                chunk = []
    return captions
