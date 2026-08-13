from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from assembly_engine.profiles import PLATFORM_PROFILES
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
from asset_engine.seed import seed_from_v2_config
from config.settings import get_settings
from db.models import Assembly
from db.session import get_session, init_db, reset_engine
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService

app = typer.Typer(
    help="Assembly Engine — AssemblySpecification → validated final reel",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


def _write_stub_media(
    path: Path,
    *,
    kind: str,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    extra: dict | None = None,
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
        **(extra or {}),
    }
    marker = b"AMP_VIDEO_STUB\n" if kind == "video" else b"AMP_AUDIO_STUB\n"
    path.write_bytes(marker + json.dumps(payload).encode("utf-8"))
    path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")


def _bootstrap_spec(session, character: str) -> tuple[AssemblySpecification, str]:
    seed_from_v2_config(session)
    settings = get_settings()
    storage = Path(settings.storage_root)

    stories = StoryService(session).generate(
        StoryRequest.model_validate(
            {
                "content_opportunity": {
                    "topic": "POV horror",
                    "emotion": "fear",
                    "platform": "instagram_reels",
                },
                "creative_direction": {
                    "format": "POV",
                    "target_duration_sec": 30,
                    "visual_style": "cinematic_horror",
                },
                "characters": [{"character_slug": character, "role": "protagonist"}],
                "candidate_count": 1,
                "story_type": "pov_horror",
            }
        )
    )
    board = StoryboardService(session).generate(
        StoryboardRequest(
            story_id=stories[0].id,
            character_slugs=[character],
            location_query="Haunted School",
        )
    )
    duration = float(board.duration_sec or 30)
    scenes_doc = (board.document or {}).get("scenes") or []
    if not scenes_doc:
        scenes_doc = [
            {"id": "s1", "start_time_sec": 0, "end_time_sec": 10},
            {"id": "s2", "start_time_sec": 10, "end_time_sec": 20},
            {"id": "s3", "start_time_sec": 20, "end_time_sec": duration},
        ]

    scenes: list[SceneBlock] = []
    video_clips: list[ClipSpec] = []
    for sc in scenes_doc:
        sid = str(sc.get("id") or f"scene_{uuid4().hex[:6]}")
        start = float(sc.get("start_time_sec") or 0)
        end = float(sc.get("end_time_sec") or start + 4)
        scenes.append(SceneBlock(scene_id=sid, start=start, end=end))
        vid = f"video_{uuid4().hex[:8]}"
        path = storage / "generated" / "video" / "assembly_bootstrap" / f"{vid}.mp4"
        _write_stub_media(path, kind="video", duration=max(0.8, end - start))
        video_clips.append(
            ClipSpec(
                artifact_id=vid,
                storage_uri=str(path),
                start=start,
                end=end,
                source_end=end - start,
                focal_point={"x": 0.5, "y": 0.45, "subject": "character"},
            )
        )

    # Image Ken Burns filler for first gap-style beat
    img_id = f"image_{uuid4().hex[:8]}"
    img_path = storage / "generated" / "image" / "assembly_bootstrap" / f"{img_id}.png"
    _write_stub_media(img_path, kind="image", duration=2.0)
    image_clips = [
        ClipSpec(
            artifact_id=img_id,
            storage_uri=str(img_path),
            start=min(4.0, duration * 0.15),
            end=min(6.0, duration * 0.15 + 2.0),
            transform=TransformSpec(scale_start=1.0, scale_end=1.08),
        )
    ]

    voice_id = f"voice_{uuid4().hex[:8]}"
    voice_path = storage / "generated" / "voice" / "assembly_bootstrap" / f"{voice_id}.wav"
    _write_stub_media(
        voice_path,
        kind="voice",
        duration=2.4,
        extra={
            "timestamps": {
                "words": [
                    {"word": "Don't", "start": 0.0, "end": 0.35},
                    {"word": "open", "start": 0.35, "end": 0.7},
                    {"word": "that", "start": 0.7, "end": 1.0},
                    {"word": "door.", "start": 1.0, "end": 1.6},
                ]
            }
        },
    )
    voice_clips = [
        AudioClipSpec(
            artifact_id=voice_id,
            storage_uri=str(voice_path),
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
    ]

    music_id = f"music_{uuid4().hex[:8]}"
    music_path = storage / "generated" / "audio" / "assembly_bootstrap" / f"{music_id}.wav"
    _write_stub_media(music_path, kind="music", duration=20.0)
    music_clips = [
        AudioClipSpec(
            artifact_id=music_id,
            storage_uri=str(music_path),
            start=0.0,
            end=duration,
            volume_db=-12.0,
            fade_in_ms=500,
            fade_out_ms=1000,
            loop=True,
        )
    ]

    sfx_id = f"sfx_{uuid4().hex[:8]}"
    sfx_path = storage / "generated" / "audio" / "assembly_bootstrap" / f"{sfx_id}.wav"
    _write_stub_media(sfx_path, kind="sfx", duration=1.0)
    sfx_clips = [
        AudioClipSpec(
            artifact_id=sfx_id,
            storage_uri=str(sfx_path),
            start=12.4 if duration > 13 else max(1.0, duration * 0.4),
            end=13.2 if duration > 13 else max(1.8, duration * 0.4 + 0.8),
            volume_db=-5.0,
        )
    ]

    silences = [SilenceSpec(start=14.2, end=14.6, reason="twist")] if duration >= 15 else []
    captions = [
        CaptionClipSpec(
            text="DON'T OPEN THAT DOOR.",
            start=0.2,
            end=1.8,
            style="bold",
            position="bottom_safe",
            words=[
                {"word": "Don't", "start": 0.2, "end": 0.55},
                {"word": "open", "start": 0.55, "end": 0.9},
                {"word": "that", "start": 0.9, "end": 1.2},
                {"word": "door.", "start": 1.2, "end": 1.8},
            ],
        )
    ]
    overlays = [
        OverlaySpec(
            text="You wouldn't open this door...",
            start=0.0,
            end=2.5,
            position={"x": 0.5, "y": 0.15},
            role="hook",
        ),
        OverlaySpec(
            text="Follow for Part 2",
            start=max(0.0, duration - 3.5),
            end=duration,
            position={"x": 0.5, "y": 0.18},
            role="cta",
        ),
    ]
    effects = [
        EffectSpec(type="shake", start=silences[0].end, end=silences[0].end + 0.4, intensity=0.6)
        for _ in ([1] if silences else [])
    ]

    content_id = f"content_{board.id[:8]}"
    spec = AssemblySpecification(
        content_id=content_id,
        storyboard_id=board.id,
        duration_sec=duration,
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
        ducking=DuckingSpec(target_db=-20, bed_db=-12),
        captions_enabled=True,
        effects_enabled=True,
        platform_profile="instagram_reels_v1",
        lineage={"storyboard_id": board.id, "character": character, "bootstrap": True},
    )
    return spec, board.id


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str = typer.Option("ghost_kid", "--character", "-c"),
    quality: str = typer.Option("final", "--quality"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Bootstrap storyboard + stub assets → assemble → render final reel."""
    _init()
    with get_session() as session:
        if not bootstrap:
            console.print("[red]Provide --bootstrap for the V1 acceptance path[/red]")
            raise typer.Exit(1)
        spec, board_id = _bootstrap_spec(session, character)
        assembly = AssemblyService(session).create(
            CreateAssemblyRequest(
                content_id=spec.content_id,
                storyboard_id=board_id,
                specification=spec,
                process_render=True,
                render_quality=quality,  # type: ignore[arg-type]
            )
        )
        arts = AssemblyService(session).list_artifacts(assembly.id)
        payload = {
            "assembly_id": assembly.id,
            "version": assembly.version,
            "status": assembly.status,
            "duration_sec": float(assembly.duration_sec or 0),
            "storyboard_id": board_id,
            "artifact_id": arts[0].id if arts else None,
            "storage_uri": arts[0].storage_uri if arts else None,
            "width": arts[0].width if arts else None,
            "height": arts[0].height if arts else None,
        }
        if json_out:
            console.print_json(data=payload)
        else:
            console.print(
                Panel.fit(
                    f"[bold]Assembly[/bold] {assembly.id[:8]} v{assembly.version}\n"
                    f"status={assembly.status} duration={payload['duration_sec']}s\n"
                    f"artifact={payload['artifact_id'] and payload['artifact_id'][:8]}\n"
                    f"uri={payload['storage_uri']}",
                    title="assemble run",
                )
            )


@app.command("create")
def create_cmd(
    spec_file: Path = typer.Argument(..., exists=True, dir_okay=False),
    render: bool = typer.Option(False, "--render"),
    quality: str = typer.Option("final", "--quality"),
) -> None:
    """Create an assembly from a JSON AssemblySpecification file."""
    _init()
    data = json.loads(spec_file.read_text(encoding="utf-8"))
    with get_session() as session:
        row = AssemblyService(session).create(
            CreateAssemblyRequest(
                specification=data,
                process_render=render,
                render_quality=quality,  # type: ignore[arg-type]
            )
        )
        console.print(f"created {row.id} status={row.status} v{row.version}")


@app.command("show")
def show_cmd(assembly_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        row = AssemblyService(session).get_assembly(assembly_id)
        if not row:
            console.print("[red]not found[/red]")
            raise typer.Exit(1)
        console.print_json(
            data={
                "id": row.id,
                "content_id": row.content_id,
                "version": row.version,
                "status": row.status,
                "duration_sec": float(row.duration_sec or 0),
                "platform_profile": row.platform_profile,
                "timeline_tracks": [
                    t.get("type") for t in ((row.timeline or {}).get("tracks") or [])
                ],
            }
        )


@app.command("validate")
def validate_cmd(assembly_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        row = AssemblyService(session).validate(assembly_id)
        console.print(f"{row.id[:8]} → {row.status}")


@app.command("render")
def render_cmd(
    assembly_id: str = typer.Argument(...),
    quality: str = typer.Option("final", "--quality"),
    profile: str | None = typer.Option(None, "--profile"),
) -> None:
    _init()
    with get_session() as session:
        job = AssemblyService(session).render(
            RenderRequestIn(
                assembly_id=assembly_id,
                quality=quality,  # type: ignore[arg-type]
                render_profile=profile,
                process=True,
            )
        )
        console.print(f"render {job.id[:8]} status={job.status} progress={job.progress}")


@app.command("render-status")
def render_status_cmd(render_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        job = AssemblyService(session).get_render(render_id)
        if not job:
            console.print("[red]not found[/red]")
            raise typer.Exit(1)
        console.print_json(
            data={
                "render_id": job.id,
                "status": job.status,
                "progress": float(job.progress or 0),
                "quality": job.quality,
                "error": job.error,
            }
        )


@app.command("artifacts")
def artifacts_cmd(assembly_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        arts = AssemblyService(session).list_artifacts(assembly_id)
        table = Table(title="Rendered artifacts")
        table.add_column("id")
        table.add_column("type")
        table.add_column("WxH")
        table.add_column("duration")
        table.add_column("uri")
        for a in arts:
            table.add_row(
                a.id[:8],
                a.artifact_type,
                f"{a.width}x{a.height}",
                str(a.duration_sec),
                (a.storage_uri or "")[-48:],
            )
        console.print(table)


@app.command("list")
def list_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    _init()
    with get_session() as session:
        rows = list(
            session.scalars(select(Assembly).order_by(Assembly.created_at.desc()).limit(limit)).all()
        )
        table = Table(title="Assemblies")
        table.add_column("id")
        table.add_column("content")
        table.add_column("v")
        table.add_column("status")
        table.add_column("duration")
        for r in rows:
            table.add_row(
                r.id[:8],
                r.content_id[:12],
                str(r.version),
                r.status,
                str(r.duration_sec),
            )
        console.print(table)


@app.command("profiles")
def profiles_cmd() -> None:
    table = Table(title="Platform / render profiles")
    table.add_column("id")
    table.add_column("platform")
    table.add_column("resolution")
    table.add_column("fps")
    for pid, p in PLATFORM_PROFILES.items():
        c = p["canvas"]
        table.add_row(pid, p["platform"], f"{c.width}x{c.height}", str(c.fps))
    console.print(table)


if __name__ == "__main__":
    app()
