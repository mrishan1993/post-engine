from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from assembly_engine.profiles import get_platform_profile
from assembly_engine.resolve import (
    load_audio_timeline,
    load_voice_timeline,
    resolve_storage_uri,
)
from assembly_engine.schemas import (
    AssemblySpecification,
    AudioClipSpec,
    CanvasSpec,
    ClipSpec,
    DuckingSpec,
    EffectSpec,
    ExportSpec,
    OverlaySpec,
    SceneBlock,
    SilenceSpec,
    TransformSpec,
    TransitionSpec,
)
from assembly_engine.timeline import captions_from_voice_timestamps
from db.models import Storyboard


def build_specification_from_assets(
    session: Session,
    *,
    content_id: str,
    storyboard_id: str | None = None,
    video_artifact_ids: list[str] | None = None,
    image_artifact_ids: list[str] | None = None,
    voice_timeline_id: str | None = None,
    music_artifact_id: str | None = None,
    audio_timeline_id: str | None = None,
    platform_profile: str = "instagram_reels_v1",
    captions_enabled: bool = True,
) -> AssemblySpecification:
    """Compose AssemblySpecification from storyboard timing + generated artifact refs."""
    profile = get_platform_profile(platform_profile)
    canvas: CanvasSpec = profile["canvas"]
    export: ExportSpec = profile["export"]

    scenes: list[SceneBlock] = []
    duration = 30.0
    board = None
    if storyboard_id:
        board = session.get(Storyboard, storyboard_id)
        if board:
            duration = float(board.duration_sec or duration)
            doc = board.document or {}
            for sc in doc.get("scenes") or []:
                scenes.append(
                    SceneBlock(
                        scene_id=str(sc.get("id") or f"scene_{uuid4().hex[:6]}"),
                        start=float(sc.get("start_time_sec") or 0),
                        end=float(sc.get("end_time_sec") or 0),
                        transition=TransitionSpec(type="cut"),
                        metadata={
                            "narrative_function": sc.get("narrative_function"),
                            "focal_point": (sc.get("shots") or [{}])[0].get("composition"),
                        },
                    )
                )
            if scenes:
                duration = max(duration, max(s.end for s in scenes))

    video_clips: list[ClipSpec] = []
    vids = video_artifact_ids or []
    if vids and scenes:
        # Map videos onto scenes in order
        for i, scene in enumerate(scenes):
            aid = vids[min(i, len(vids) - 1)]
            uri, meta = resolve_storage_uri(session, aid)
            video_clips.append(
                ClipSpec(
                    artifact_id=aid,
                    storage_uri=uri,
                    start=scene.start,
                    end=scene.end,
                    source_start=0.0,
                    source_end=scene.end - scene.start,
                    transition=scene.transition,
                    focal_point={"x": 0.5, "y": 0.45, "subject": "character"},
                    metadata=meta,
                )
            )
    elif vids:
        # Equal split across duration
        slot = duration / len(vids)
        t = 0.0
        for aid in vids:
            uri, meta = resolve_storage_uri(session, aid)
            video_clips.append(
                ClipSpec(
                    artifact_id=aid,
                    storage_uri=uri,
                    start=round(t, 3),
                    end=round(t + slot, 3),
                    source_end=slot,
                    metadata=meta,
                )
            )
            t += slot

    image_clips: list[ClipSpec] = []
    for i, aid in enumerate(image_artifact_ids or []):
        uri, meta = resolve_storage_uri(session, aid)
        # Place leftover images as Ken Burns fillers if no video coverage gap — append after videos
        start = duration + i * 2.0 if not video_clips else float(video_clips[min(i, len(video_clips) - 1)].start)
        end = start + 2.0
        image_clips.append(
            ClipSpec(
                artifact_id=aid,
                storage_uri=uri,
                start=start,
                end=end,
                transform=TransformSpec(scale_start=1.0, scale_end=1.08),
                metadata=meta,
            )
        )

    voice_clips: list[AudioClipSpec] = []
    if voice_timeline_id:
        vtl = load_voice_timeline(session, voice_timeline_id)
        if vtl:
            for seg in vtl.segments or []:
                aid = seg.get("artifact_id")
                if not aid:
                    continue
                uri, meta = resolve_storage_uri(session, aid)
                voice_clips.append(
                    AudioClipSpec(
                        artifact_id=aid,
                        storage_uri=uri,
                        start=float(seg.get("start") or 0),
                        end=float(seg.get("end") or 0),
                        volume_db=0.0,
                        metadata={
                            **meta,
                            "speaker": seg.get("speaker"),
                            "dialogue_id": seg.get("dialogue_id"),
                            "timestamps": meta.get("timestamps"),
                        },
                    )
                )

    music_clips: list[AudioClipSpec] = []
    sfx_clips: list[AudioClipSpec] = []
    silences: list[SilenceSpec] = []
    ducking = DuckingSpec()
    beat_grid: list[float] = []

    if audio_timeline_id:
        atl = load_audio_timeline(session, audio_timeline_id)
        if atl:
            beat_grid = list(atl.beat_grid or [])
            duck_cfg = atl.ducking or {}
            ducking = DuckingSpec(
                target_db=float(duck_cfg.get("music_duck_db") or -20),
                bed_db=float(duck_cfg.get("music_bed_db") or -12),
            )
            for tr in atl.tracks or []:
                ttype = tr.get("type")
                if ttype == "silence":
                    silences.append(
                        SilenceSpec(
                            start=float(tr.get("start") or 0),
                            end=float(tr.get("end") or 0),
                            reason=str((tr.get("metadata") or {}).get("reason") or "dramatic"),
                        )
                    )
                    continue
                aid = tr.get("artifact_id")
                if not aid and ttype != "ambience":
                    continue
                uri, meta = (None, {})
                if aid:
                    uri, meta = resolve_storage_uri(session, aid)
                clip = AudioClipSpec(
                    artifact_id=aid or f"ambience_{uuid4().hex[:6]}",
                    storage_uri=uri,
                    start=float(tr.get("start") or 0),
                    end=float(tr.get("end") or duration),
                    volume_db=float(tr.get("gain_db") or 0),
                    fade_in_ms=int((tr.get("fade_in_sec") or 0) * 1000),
                    fade_out_ms=int((tr.get("fade_out_sec") or 0) * 1000),
                    metadata={**meta, **(tr.get("metadata") or {})},
                )
                if ttype == "music":
                    music_clips.append(clip)
                elif ttype == "sfx":
                    sfx_clips.append(clip)

    if music_artifact_id and not music_clips:
        uri, meta = resolve_storage_uri(session, music_artifact_id)
        music_clips.append(
            AudioClipSpec(
                artifact_id=music_artifact_id,
                storage_uri=uri,
                start=0.0,
                end=duration,
                volume_db=ducking.bed_db,
                fade_in_ms=500,
                fade_out_ms=1000,
                loop=True,
                metadata=meta,
            )
        )

    captions = []
    if captions_enabled and voice_clips:
        captions = captions_from_voice_timestamps(
            [c.model_dump() for c in voice_clips], style="bold"
        )

    overlays: list[OverlaySpec] = []
    effects: list[EffectSpec] = []
    # CTA from last scene if present
    if scenes:
        last = scenes[-1]
        if (last.metadata or {}).get("narrative_function") == "cta" or last.end >= duration - 5:
            overlays.append(
                OverlaySpec(
                    text="Follow for Part 2",
                    start=max(0.0, duration - 3.5),
                    end=duration,
                    position={"x": 0.5, "y": 0.18},
                    role="cta",
                )
            )
        # Impact shake near twist silence
        for sil in silences:
            if sil.reason in {"twist", "dramatic", "pattern_interrupt", "shot_silence"}:
                effects.append(
                    EffectSpec(
                        type="shake",
                        start=sil.end,
                        end=round(sil.end + 0.4, 3),
                        intensity=0.6,
                    )
                )

    return AssemblySpecification(
        content_id=content_id,
        storyboard_id=storyboard_id,
        canvas=canvas,
        duration_sec=round(duration, 3),
        scenes=scenes,
        video_clips=video_clips,
        image_clips=image_clips,
        voice_clips=voice_clips,
        music_clips=music_clips,
        sfx_clips=sfx_clips,
        captions=captions,
        overlays=overlays,
        effects=effects,
        silences=silences,
        ducking=ducking,
        beat_grid=beat_grid,
        captions_enabled=captions_enabled,
        effects_enabled=True,
        export=export,
        platform_profile=platform_profile,
        lineage={
            "storyboard_id": storyboard_id,
            "voice_timeline_id": voice_timeline_id,
            "audio_timeline_id": audio_timeline_id,
            "video_artifact_ids": video_artifact_ids or [],
            "music_artifact_id": music_artifact_id,
        },
    )
