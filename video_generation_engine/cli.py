from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import VideoGenerationRequest
from db.session import get_session, init_db, reset_engine
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService
from video_generation_engine.capabilities import list_video_providers
from video_generation_engine.schemas import ProviderStrategy, VideoGenerationRequestIn
from video_generation_engine.service import VideoGenerationService

app = typer.Typer(
    help="Video Generation Engine — PromptPackage → validated video clips",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("run")
def run_cmd(
    package_id: str | None = typer.Option(None, "--package", "-p"),
    storyboard_id: str | None = typer.Option(None, "--storyboard", "-b"),
    variants: int = typer.Option(2, "--variants", "-n"),
    provider: str = typer.Option("provider_a", "--provider"),
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str | None = typer.Option(None, "--character", "-c"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """V1 acceptance path: storyboard/prompt → video artifacts (stub provider)."""
    _init()
    with get_session() as session:
        if bootstrap and not package_id and not storyboard_id:
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

        if not package_id and not storyboard_id:
            console.print("[red]Provide --package, --storyboard, or --bootstrap[/red]")
            raise typer.Exit(1)

        req = VideoGenerationService(session).create(
            VideoGenerationRequestIn(
                prompt_package_id=package_id,
                storyboard_id=storyboard_id,
                variants={"count": variants, "strategy": "mixed"},
                provider_strategy=ProviderStrategy(
                    mode="preferred",
                    preferred=provider,
                    fallback=["provider_b"],
                ),
                priority="high",
                process=True,
            )
        )
        arts = VideoGenerationService(session).list_artifacts(req.id)
        if json_out:
            console.print_json(
                json.dumps(
                    {
                        "request_id": req.id,
                        "status": req.status,
                        "artifacts": [
                            {
                                "artifact_id": a.id,
                                "status": "completed",
                                "video_url": a.storage_uri,
                                "duration_sec": float(a.duration_sec or 0),
                                "width": a.width,
                                "height": a.height,
                                "provider": a.provider,
                                "sha256": a.sha256,
                            }
                            for a in arts
                        ],
                    },
                    default=str,
                )
            )
            return

        console.print(
            Panel.fit(
                f"status={req.status} artifacts={len(arts)} variants={req.variant_count}",
                title=req.id,
            )
        )
        for a in arts:
            console.print(
                f"  [green]{a.id[:8]}[/green] {a.width}x{a.height} "
                f"{float(a.duration_sec or 0):.1f}s → {a.storage_uri}"
            )


@app.command("show")
def show_cmd(request_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        req = session.get(VideoGenerationRequest, request_id)
        if not req:
            rows = list(
                session.scalars(
                    select(VideoGenerationRequest).where(
                        VideoGenerationRequest.id.startswith(request_id)
                    )
                ).all()
            )
            if len(rows) != 1:
                console.print("[red]Not found[/red]")
                raise typer.Exit(1)
            req = rows[0]
        jobs = VideoGenerationService(session).list_jobs(req.id)
        table = Table(title=f"Video Jobs — {req.id[:8]}")
        table.add_column("Job")
        table.add_column("Var")
        table.add_column("Provider")
        table.add_column("Status")
        table.add_column("Cost")
        for j in jobs:
            table.add_row(
                j.id[:8],
                str(j.variant_number),
                j.provider or "",
                j.status,
                f"{float(j.actual_cost or j.estimated_cost or 0):.3f}",
            )
        console.print(table)


@app.command("artifacts")
def artifacts_cmd(request_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        reqs = [session.get(VideoGenerationRequest, request_id)]
        if not reqs[0]:
            reqs = list(
                session.scalars(
                    select(VideoGenerationRequest).where(
                        VideoGenerationRequest.id.startswith(request_id)
                    )
                ).all()
            )
        if len(reqs) != 1 or not reqs[0]:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        for a in VideoGenerationService(session).list_artifacts(reqs[0].id):
            console.print_json(
                json.dumps(
                    {
                        "artifact_id": a.id,
                        "video_url": a.storage_uri,
                        "duration_sec": float(a.duration_sec or 0),
                        "width": a.width,
                        "height": a.height,
                        "provider": a.provider,
                        "technical_qa": a.technical_qa,
                    },
                    default=str,
                )
            )


@app.command("providers")
def providers_cmd() -> None:
    table = Table(title="Video Providers")
    table.add_column("ID")
    table.add_column("Model")
    table.add_column("Max Dur")
    table.add_column("Ratios")
    for p in list_video_providers():
        limits = p.get("limits") or {}
        table.add_row(
            p["id"],
            str(p.get("model") or ""),
            str(limits.get("max_duration_sec") or ""),
            ",".join(limits.get("supported_ratios") or []),
        )
    console.print(table)


if __name__ == "__main__":
    app()
