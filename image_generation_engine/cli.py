from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import ImageArtifact, ImageGenerationRequest
from db.session import get_session, init_db, reset_engine
from image_generation_engine.capabilities import list_image_providers
from image_generation_engine.schemas import (
    ImageEditRequestIn,
    ImageGenerationRequestIn,
    ProviderStrategy,
)
from image_generation_engine.service import ImageGenerationService
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService

app = typer.Typer(
    help="Image Generation Engine — ImagePromptPackage → validated image artifacts",
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
    purpose: str = typer.Option("storyboard_keyframe", "--purpose"),
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str | None = typer.Option(None, "--character", "-c"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """V1 acceptance path: storyboard/prompt → image artifacts (stub provider)."""
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

        req = ImageGenerationService(session).create(
            ImageGenerationRequestIn(
                prompt_package_id=package_id,
                storyboard_id=storyboard_id,
                purpose=purpose,  # type: ignore[arg-type]
                variants={"count": variants, "strategy": "different_composition"},
                provider_strategy=ProviderStrategy(
                    mode="preferred",
                    preferred=provider,
                    fallback=["provider_b"],
                ),
                priority="high",
                process=True,
            )
        )
        arts = ImageGenerationService(session).list_artifacts(req.id)
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
                                "url": a.storage_uri,
                                "width": a.width,
                                "height": a.height,
                                "provider": a.provider,
                                "model": a.model,
                                "quality_score": (a.technical_qa or {}).get("technical_score"),
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
                f"status={req.status} artifacts={len(arts)} purpose={req.purpose}",
                title=req.id,
            )
        )
        for a in arts:
            score = (a.technical_qa or {}).get("technical_score")
            console.print(
                f"  [green]{a.id[:8]}[/green] {a.width}x{a.height} "
                f"qa={score} → {a.storage_uri}"
            )


@app.command("show")
def show_cmd(request_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        req = session.get(ImageGenerationRequest, request_id)
        if not req:
            rows = list(
                session.scalars(
                    select(ImageGenerationRequest).where(
                        ImageGenerationRequest.id.startswith(request_id)
                    )
                ).all()
            )
            if len(rows) != 1:
                console.print("[red]Not found[/red]")
                raise typer.Exit(1)
            req = rows[0]
        jobs = ImageGenerationService(session).list_jobs(req.id)
        table = Table(title=f"Image Jobs — {req.id[:8]}")
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
        reqs = [session.get(ImageGenerationRequest, request_id)]
        if not reqs[0]:
            reqs = list(
                session.scalars(
                    select(ImageGenerationRequest).where(
                        ImageGenerationRequest.id.startswith(request_id)
                    )
                ).all()
            )
        if len(reqs) != 1 or not reqs[0]:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        for a in ImageGenerationService(session).list_artifacts(reqs[0].id):
            console.print_json(
                json.dumps(
                    {
                        "artifact_id": a.id,
                        "url": a.storage_uri,
                        "width": a.width,
                        "height": a.height,
                        "provider": a.provider,
                        "model": a.model,
                        "parent_artifact_id": a.parent_artifact_id,
                        "quality_score": (a.technical_qa or {}).get("technical_score"),
                        "technical_qa": a.technical_qa,
                    },
                    default=str,
                )
            )


@app.command("edit")
def edit_cmd(
    artifact_id: str = typer.Argument(...),
    instruction: str = typer.Option(..., "--instruction", "-i"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Edit an existing artifact → new versioned artifact (never overwrites)."""
    _init()
    with get_session() as session:
        req = ImageGenerationService(session).edit(
            ImageEditRequestIn(artifact_id=artifact_id, instruction=instruction, process=True)
        )
        arts = ImageGenerationService(session).list_artifacts(req.id)
        if json_out:
            console.print_json(
                json.dumps(
                    {
                        "request_id": req.id,
                        "status": req.status,
                        "artifacts": [
                            {
                                "artifact_id": a.id,
                                "parent_artifact_id": a.parent_artifact_id,
                                "url": a.storage_uri,
                            }
                            for a in arts
                        ],
                    },
                    default=str,
                )
            )
            return
        console.print(f"edit request {req.id[:8]} status={req.status} artifacts={len(arts)}")


@app.command("providers")
def providers_cmd() -> None:
    table = Table(title="Image Providers")
    table.add_column("ID")
    table.add_column("Model")
    table.add_column("Max Refs")
    table.add_column("Ratios")
    for p in list_image_providers():
        limits = p.get("limits") or {}
        table.add_row(
            p["id"],
            str(p.get("model") or ""),
            str(limits.get("max_references") or ""),
            ",".join(limits.get("supported_ratios") or []),
        )
    console.print(table)


if __name__ == "__main__":
    app()
