from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import GenerationJob, GenerationRequest, MediaArtifact, ProviderPerformance
from db.session import get_session, init_db, reset_engine
from generation_engine.providers.registry import list_generation_providers
from generation_engine.schemas import GenerationRequestIn, ProviderStrategy, VariantsConfig
from generation_engine.service import GenerationService
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService

app = typer.Typer(
    help="Generation Engine — execute PromptPackages → media artifacts",
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
    variants: int = typer.Option(1, "--variants", "-n"),
    provider: str | None = typer.Option(None, "--provider"),
    modality: str = typer.Option("video", "--modality", "-m"),
    profile: str | None = typer.Option(None, "--profile"),
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str | None = typer.Option(None, "--character", "-c"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Queue + process a generation request (stub providers write local files)."""
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

        svc = GenerationService(session)
        if storyboard_id and not package_id:
            # single first-shot request via storyboard
            req = svc.create(
                GenerationRequestIn(
                    storyboard_id=storyboard_id,
                    modality=modality,
                    variants=VariantsConfig(count=variants),
                    provider_strategy=ProviderStrategy(
                        mode="preferred" if provider else "automatic",
                        preferred=provider,
                        fallback=["runway", "veo"],
                    ),
                    profile=profile,
                    process=True,
                )
            )
            reqs = [req]
        elif package_id:
            reqs = [
                svc.create(
                    GenerationRequestIn(
                        prompt_package_id=package_id,
                        modality=modality,
                        variants=VariantsConfig(count=variants),
                        provider_strategy=ProviderStrategy(
                            mode="preferred" if provider else "automatic",
                            preferred=provider,
                            fallback=["runway", "veo"],
                        ),
                        profile=profile,
                        process=True,
                    )
                )
            ]
        else:
            console.print("[red]Provide --package, --storyboard, or --bootstrap[/red]")
            raise typer.Exit(1)

        if json_out:
            out = []
            for r in reqs:
                arts = svc.list_artifacts(r.id)
                out.append(
                    {
                        "generation_request_id": r.id,
                        "status": r.status,
                        "jobs": [j.id for j in svc.list_jobs(r.id)],
                        "artifacts": [
                            {"id": a.id, "uri": a.storage_uri, "sha256": a.sha256} for a in arts
                        ],
                    }
                )
            console.print_json(json.dumps(out, default=str))
            return

        for r in reqs:
            jobs = svc.list_jobs(r.id)
            arts = svc.list_artifacts(r.id)
            console.print(
                Panel.fit(
                    f"status={r.status} jobs={len(jobs)} artifacts={len(arts)} "
                    f"modality={r.modality}",
                    title=r.id,
                )
            )
            for a in arts:
                console.print(f"  [green]artifact[/green] {a.id[:8]} → {a.storage_uri}")


@app.command("show")
def show_cmd(request_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        req = session.get(GenerationRequest, request_id)
        if not req:
            rows = list(
                session.scalars(
                    select(GenerationRequest).where(
                        GenerationRequest.id.startswith(request_id)
                    )
                ).all()
            )
            if len(rows) != 1:
                console.print("[red]Not found[/red]")
                raise typer.Exit(1)
            req = rows[0]
        jobs = GenerationService(session).list_jobs(req.id)
        table = Table(title=f"Jobs — {req.id[:8]}")
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
        arts = GenerationService(session).list_artifacts(request_id)
        if not arts:
            # prefix match
            reqs = list(
                session.scalars(
                    select(GenerationRequest).where(
                        GenerationRequest.id.startswith(request_id)
                    )
                ).all()
            )
            if len(reqs) == 1:
                arts = GenerationService(session).list_artifacts(reqs[0].id)
        for a in arts:
            console.print_json(
                json.dumps(
                    {
                        "id": a.id,
                        "type": a.artifact_type,
                        "uri": a.storage_uri,
                        "sha256": a.sha256,
                        "provider": a.provider,
                        "technical_qa": a.technical_qa,
                    },
                    default=str,
                )
            )


@app.command("providers")
def providers_cmd() -> None:
    table = Table(title="Generation Providers")
    table.add_column("ID")
    table.add_column("Modalities")
    table.add_column("Enabled")
    for p in list_generation_providers():
        table.add_row(
            p["id"],
            ",".join(p.get("modality") or []),
            str((p.get("status") or {}).get("enabled")),
        )
    console.print(table)


@app.command("performance")
def performance_cmd() -> None:
    _init()
    with get_session() as session:
        rows = list(session.scalars(select(ProviderPerformance)).all())
        table = Table(title="Provider Performance")
        table.add_column("Provider")
        table.add_column("Modality")
        table.add_column("Success")
        table.add_column("Avg Cost")
        table.add_column("N")
        for r in rows:
            table.add_row(
                r.provider,
                r.modality,
                f"{float(r.success_rate or 0):.2f}",
                f"{float(r.avg_cost or 0):.3f}",
                str(r.sample_count),
            )
        console.print(table)


@app.command("list")
def list_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    _init()
    with get_session() as session:
        rows = list(
            session.scalars(
                select(GenerationRequest)
                .order_by(GenerationRequest.created_at.desc())
                .limit(limit)
            ).all()
        )
        table = Table(title="Generation Requests")
        table.add_column("ID")
        table.add_column("Modality")
        table.add_column("Status")
        table.add_column("Variants")
        for r in rows:
            table.add_row(r.id[:8], r.modality, r.status, str(r.requested_variants))
        console.print(table)


if __name__ == "__main__":
    app()
