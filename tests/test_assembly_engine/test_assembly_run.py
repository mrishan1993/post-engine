from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from amp_platform.events import EventType, get_bus, reset_bus
from assembly_engine.profiles import get_platform_profile
from assembly_engine.schemas import (
    AssemblySpecification,
    AudioClipSpec,
    CaptionClipSpec,
    ClipSpec,
    CreateAssemblyRequest,
    DuckingSpec,
    EffectSpec,
    OverlaySpec,
    RenderRequestIn,
    SceneBlock,
    SilenceSpec,
    TransformSpec,
)
from assembly_engine.service import AssemblyService
from assembly_engine.state import can_transition, transition_assembly, transition_render
from assembly_engine.timeline import build_timeline, captions_from_voice_timestamps
from assembly_engine.validation import validate_assembly_spec, validate_rendered_output
from config.settings import get_settings
from db.models import Assembly, RenderJob, RenderedArtifact
from db.session import get_session


def _stub_file(
    path: Path,
    *,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    kind: str = "video",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stub": True,
        "kind": kind,
        "width": width,
        "height": height,
        "fps": 30,
        "duration_sec": duration,
        "video_codec": "h264",
        "audio_codec": "aac",
    }
    marker = b"AMP_VIDEO_STUB\n" if kind in {"video", "image"} else b"AMP_AUDIO_STUB\n"
    path.write_bytes(marker + json.dumps(payload).encode("utf-8"))
    path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")


def _build_spec(tmp: Path) -> AssemblySpecification:
    duration = 30.0
    scenes = [
        SceneBlock(scene_id="scene_001", start=0, end=4),
        SceneBlock(scene_id="scene_002", start=4, end=9),
        SceneBlock(scene_id="scene_003", start=9, end=30),
    ]
    videos = []
    for i, sc in enumerate(scenes):
        aid = f"video_{i+1:03d}"
        path = tmp / "video" / f"{aid}.mp4"
        _stub_file(path, duration=sc.end - sc.start, kind="video")
        videos.append(
            ClipSpec(
                artifact_id=aid,
                storage_uri=str(path),
                start=sc.start,
                end=sc.end,
                source_start=0,
                source_end=sc.end - sc.start,
                focal_point={"x": 0.68, "y": 0.43, "subject": "character"},
            )
        )
    img = tmp / "image" / "image_001.png"
    _stub_file(img, duration=2.0, kind="image")
    voice = tmp / "voice" / "voice_001.wav"
    _stub_file(voice, duration=2.4, kind="voice")
    music = tmp / "music" / "music_001.wav"
    _stub_file(music, duration=20.0, kind="music")
    sfx = tmp / "sfx" / "door_creak.wav"
    _stub_file(sfx, duration=0.8, kind="sfx")

    voice_clip = AudioClipSpec(
        artifact_id="voice_001",
        storage_uri=str(voice),
        start=0.2,
        end=2.6,
        metadata={
            "text": "Don't open that door.",
            "timestamps": {
                "words": [
                    {"word": "Don't", "start": 0.0, "end": 0.35},
                    {"word": "open", "start": 0.35, "end": 0.7},
                    {"word": "that", "start": 0.7, "end": 1.0},
                    {"word": "door.", "start": 1.0, "end": 1.6},
                ]
            },
        },
    )
    captions = captions_from_voice_timestamps([voice_clip.model_dump()], style="bold")
    return AssemblySpecification(
        content_id="content_001",
        duration_sec=duration,
        scenes=scenes,
        video_clips=videos,
        image_clips=[
            ClipSpec(
                artifact_id="image_001",
                storage_uri=str(img),
                start=4.0,
                end=6.0,
                transform=TransformSpec(scale_start=1.0, scale_end=1.08),
            )
        ],
        voice_clips=[voice_clip],
        music_clips=[
            AudioClipSpec(
                artifact_id="music_001",
                storage_uri=str(music),
                start=0,
                end=duration,
                volume_db=-12,
                fade_in_ms=500,
                fade_out_ms=1000,
                loop=True,
            )
        ],
        sfx_clips=[
            AudioClipSpec(
                artifact_id="door_creak",
                storage_uri=str(sfx),
                start=12.4,
                end=13.2,
                volume_db=-5,
            )
        ],
        captions=captions,
        overlays=[
            OverlaySpec(
                text="You wouldn't open this door...",
                start=0,
                end=2.5,
                role="hook",
            ),
            OverlaySpec(
                text="Follow for Part 2",
                start=26.5,
                end=30,
                role="cta",
            ),
        ],
        effects=[EffectSpec(type="shake", start=14.6, end=15.0, intensity=0.6)],
        silences=[SilenceSpec(start=14.2, end=14.6, reason="twist")],
        ducking=DuckingSpec(target_db=-20, bed_db=-12, attack_ms=80, release_ms=300),
        captions_enabled=True,
        effects_enabled=True,
        platform_profile="instagram_reels_v1",
    )


def test_state_machines() -> None:
    assert can_transition({"draft": {"validated"}}, "draft", "validated")
    assert transition_assembly("draft", "validated") == "validated"
    assert transition_render("queued", "validating") == "validating"
    with pytest.raises(ValueError):
        transition_render("completed", "rendering")


def test_timeline_tracks_and_captions() -> None:
    # Pure unit — no files required for structure
    spec = AssemblySpecification(
        content_id="c1",
        duration_sec=10,
        video_clips=[
            ClipSpec(artifact_id="v1", storage_uri="/tmp/x", start=0, end=4),
            ClipSpec(artifact_id="v2", storage_uri="/tmp/y", start=4, end=10),
        ],
        voice_clips=[
            AudioClipSpec(
                artifact_id="vo",
                storage_uri="/tmp/z",
                start=0.2,
                end=2.0,
                metadata={
                    "timestamps": {
                        "words": [
                            {"word": "Hi", "start": 0, "end": 0.3},
                            {"word": "there", "start": 0.3, "end": 0.8},
                        ]
                    }
                },
            )
        ],
        music_clips=[AudioClipSpec(artifact_id="m", storage_uri="/tmp/m", start=0, end=10)],
        sfx_clips=[AudioClipSpec(artifact_id="s", storage_uri="/tmp/s", start=5, end=5.5)],
        captions=[CaptionClipSpec(text="HI THERE", start=0.2, end=1.0)],
        ducking=DuckingSpec(),
    )
    assert not validate_assembly_spec(spec)
    tl = build_timeline(spec)
    types = {t.type for t in tl.tracks}
    assert {"video", "voice", "music", "sfx", "caption"} <= types
    caps = captions_from_voice_timestamps([spec.voice_clips[0].model_dump()])
    assert caps and "HI" in caps[0].text


def test_v1_acceptance_render(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    with get_session(db_url) as session:
        spec = _build_spec(tmp_path / "assets")
        profile = get_platform_profile("instagram_reels_v1")
        assert profile["canvas"].width == 1080
        assert profile["canvas"].height == 1920

        assembly = AssemblyService(session).create(
            CreateAssemblyRequest(
                specification=spec,
                process_render=True,
                render_quality="final",
            )
        )
        assert assembly.status == "completed"
        assert assembly.version == 1
        assert float(assembly.duration_sec or 0) == 30.0
        assert assembly.timeline and assembly.timeline.get("tracks")
        track_types = {t["type"] for t in assembly.timeline["tracks"]}
        assert "video" in track_types
        assert "voice" in track_types
        assert "music" in track_types
        assert "caption" in track_types
        assert "overlay" in track_types
        assert "effect" in track_types

        arts = AssemblyService(session).list_artifacts(assembly.id)
        assert len(arts) == 1
        art = arts[0]
        assert art.width == 1080
        assert art.height == 1920
        assert art.fps == 30
        assert art.video_codec == "h264"
        assert art.audio_codec == "aac"
        assert Path(art.storage_uri).exists()
        qa = validate_rendered_output(
            art.storage_uri,
            expected_duration=30.0,
            expected_width=1080,
            expected_height=1920,
            expected_fps=30,
        )
        assert qa.ok
        assert art.technical_qa and art.technical_qa.get("ok")
        assert art.render_metadata and art.render_metadata.get("source_hashes")

        # Versioned re-render — never overwrite
        job2 = AssemblyService(session).render(
            RenderRequestIn(assembly_id=assembly.id, quality="draft", process=True)
        )
        assert job2.status == "completed"
        arts2 = AssemblyService(session).list_artifacts(assembly.id)
        assert len(arts2) == 2
        assert {a.artifact_type for a in arts2} == {"final_video", "draft_video"}

    events = {e.event_type for e in get_bus().history}
    assert EventType.ASSEMBLY_CREATED in events
    assert EventType.ASSEMBLY_VALIDATED in events
    assert EventType.RENDER_REQUESTED in events
    assert EventType.RENDER_COMPLETED in events
    assert EventType.RENDER_ARTIFACT_CREATED in events
    assert EventType.RENDER_TECHNICAL_QA_COMPLETED in events


def test_missing_asset_fails_without_partial(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    with get_session(db_url) as session:
        spec = _build_spec(tmp_path / "assets")
        # Point one clip at a missing path
        spec.video_clips[0].storage_uri = str(tmp_path / "does_not_exist.mp4")
        assembly = AssemblyService(session).create(
            CreateAssemblyRequest(specification=spec, process_render=False)
        )
        job = AssemblyService(session).render(
            RenderRequestIn(assembly_id=assembly.id, process=True)
        )
        assert job.status == "failed"
        assert job.error and "MISSING_ASSET" in str(job.error.get("message") or "")
        arts = list(
            session.scalars(
                select(RenderedArtifact).where(RenderedArtifact.assembly_id == assembly.id)
            ).all()
        )
        assert arts == []
    assert EventType.RENDER_FAILED in {e.event_type for e in get_bus().history}


def test_voice_past_duration_rejected() -> None:
    spec = AssemblySpecification(
        content_id="c",
        duration_sec=5,
        video_clips=[ClipSpec(artifact_id="v", storage_uri="/x", start=0, end=5)],
        voice_clips=[AudioClipSpec(artifact_id="vo", storage_uri="/y", start=0, end=6)],
    )
    issues = validate_assembly_spec(spec)
    assert any("voice clip" in i for i in issues)


def test_update_creates_new_version(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    with get_session(db_url) as session:
        spec = _build_spec(tmp_path / "assets")
        a1 = AssemblyService(session).create(
            CreateAssemblyRequest(specification=spec, process_render=False)
        )
        spec.duration_sec = 28.0
        a2 = AssemblyService(session).update_specification(a1.id, spec)
        assert a2.id != a1.id
        assert a2.version == 2
        assert a2.lineage and a2.lineage.get("previous_assembly_id") == a1.id
