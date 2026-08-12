from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import AudioTimelineRow, MusicGenerationRequest
from db.session import get_session, init_db, reset_engine
from music_sfx_engine.capabilities import list_music_providers
from music_sfx_engine.schemas import MusicGenerationRequestIn, ProviderStrategy
from music_sfx_engine.service import MusicSfxService
from music_sfx_engine.sfx_library import seed_sfx_library
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService

app = typer.Typer(
    help="Music & SFX Engine — AudioBlueprint → music/SFX + AudioTimeline",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("run")
def run_cmd(
    storyboard_id: str | None = typer.Option(None, "--storyboard", "-b"),
    story_id: str | None = typer.Option(None, "--story", "-s"),
    variants: int = typer.Option(1, "--variants", "-n"),
    provider: str = typer.Option("provider_a", "--provider"),
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str | None = typer.Option(None, "--character", "-c"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Acceptance: storyboard → blueprint → music + SFX + timeline."""
    _init()
    with get_session() as session:
        seed_sfx_library(session)
        if bootstrap and not storyboard_id and not story_id:
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
                        "characters": (
                            [{"character_slug": character, "role": "protagonist"}]
                            if character
                            else []
                        ),
                        "candidate_count": 1,
                        "story_type": "pov_horror",
                    }
                )
            )
            board = StoryboardService(session).generate(
                StoryboardRequest(
                    story_id=stories[0].id,
                    character_slugs=[character] if character else [],
                    location_query="Haunted School",
                )
            )
            storyboard_id = board.id
            console.print(f"[dim]Bootstrapped storyboard[/dim] {storyboard_id[:8]}")

        if not storyboard_id and not story_id:
            console.print("[red]Provide --storyboard, --story, or --bootstrap[/red]")
            raise typer.Exit(1)

        req = MusicSfxService(session).create(
            MusicGenerationRequestIn(
                storyboard_id=storyboard_id,
                story_id=story_id,
                variants={"count": variants},
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred=provider, fallback=["provider_b"]
                ),
                priority="high",
                process=True,
                build_timeline=True,
                resolve_sfx=True,
            )
        )
        music = MusicSfxService(session).list_music_artifacts(req.id)
        sfx = MusicSfxService(session).list_sfx_for_request(req.id)
        tl = session.scalar(
            select(AudioTimelineRow)
            .where(AudioTimelineRow.music_request_id == req.id)
            .order_by(AudioTimelineRow.created_at.desc())
        )
        if json_out:
            console.print_json(
                json.dumps(
                    {
                        "request_id": req.id,
                        "status": req.status,
                        "music": [
                            {
                                "artifact_id": a.id,
                                "url": a.storage_uri,
                                "duration_sec": float(a.duration_sec or 0),
                                "provider": a.provider,
                                "quality_score": (a.technical_qa or {}).get("technical_score"),
                            }
                            for a in music
                        ],
                        "sfx": [
                            {
                                "artifact_id": a.id,
                                "type": (a.metadata_json or {}).get("type"),
                                "start_sec": (a.metadata_json or {}).get("start_sec"),
                                "source": (a.metadata_json or {}).get("source"),
                            }
                            for a in sfx
                        ],
                        "timeline_id": tl.id if tl else None,
                        "track_count": len(tl.tracks or []) if tl else 0,
                    },
                    default=str,
                )
            )
            return

        console.print(
            Panel.fit(
                f"status={req.status} music={len(music)} sfx={len(sfx)} "
                f"timeline={tl.id[:8] if tl else '-'}",
                title=req.id,
            )
        )
        for a in music:
            console.print(
                f"  [green]music[/green] {a.id[:8]} {float(a.duration_sec or 0):.1f}s → {a.storage_uri}"
            )
        for a in sfx[:8]:
            meta = a.metadata_json or {}
            console.print(
                f"  [cyan]sfx[/cyan] {meta.get('type')} @{meta.get('start_sec')} "
                f"({meta.get('source')})"
            )


@app.command("timeline")
def timeline_cmd(request_or_timeline_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        tl = MusicSfxService(session).get_timeline(request_or_timeline_id)
        if not tl:
            tl = session.scalar(
                select(AudioTimelineRow).where(
                    AudioTimelineRow.music_request_id.startswith(request_or_timeline_id)
                )
            )
        if not tl:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        console.print_json(
            json.dumps(
                {
                    "timeline_id": tl.id,
                    "duration_sec": float(tl.duration_sec),
                    "tracks": tl.tracks,
                    "beat_grid_len": len(tl.beat_grid or []),
                    "ducking": tl.ducking,
                    "loudness_profile": tl.loudness_profile,
                },
                default=str,
            )
        )


@app.command("sfx-search")
def sfx_search_cmd(
    query: str = typer.Argument(""),
    category: str | None = typer.Option(None, "--category"),
) -> None:
    _init()
    with get_session() as session:
        rows = MusicSfxService(session).search_sfx_library(query=query or None, category=category)
        table = Table(title="SFX Library")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Category")
        table.add_column("Dur")
        table.add_column("Tags")
        for r in rows:
            table.add_row(
                r.id[:8],
                r.name,
                f"{r.category}/{r.subtype or '-'}",
                f"{float(r.duration_sec):.2f}",
                ",".join((r.tags or [])[:4]),
            )
        console.print(table)


@app.command("providers")
def providers_cmd() -> None:
    table = Table(title="Music Providers")
    table.add_column("ID")
    table.add_column("Model")
    table.add_column("Max Dur")
    table.add_column("Genres")
    for p in list_music_providers():
        limits = p.get("limits") or {}
        caps = p.get("capabilities") or {}
        table.add_row(
            p["id"],
            str(p.get("model") or ""),
            str(limits.get("max_duration_sec") or ""),
            ",".join((caps.get("genres") or [])[:3]),
        )
    console.print(table)


@app.command("show")
def show_cmd(request_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        req = session.get(MusicGenerationRequest, request_id)
        if not req:
            rows = list(
                session.scalars(
                    select(MusicGenerationRequest).where(
                        MusicGenerationRequest.id.startswith(request_id)
                    )
                ).all()
            )
            if len(rows) != 1:
                console.print("[red]Not found[/red]")
                raise typer.Exit(1)
            req = rows[0]
        jobs = MusicSfxService(session).list_jobs(req.id)
        table = Table(title=f"Music Jobs — {req.id[:8]}")
        table.add_column("Job")
        table.add_column("Var")
        table.add_column("Provider")
        table.add_column("Status")
        for j in jobs:
            table.add_row(j.id[:8], str(j.variant_number), j.provider or "", j.status)
        console.print(table)


if __name__ == "__main__":
    app()
