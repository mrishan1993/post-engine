from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import PromptPackage, PromptSpec, Storyboard
from db.session import get_session, init_db, reset_engine
from prompt_engine.registry import list_providers, rank_providers
from prompt_engine.schemas import CompileRequest
from prompt_engine.service import PromptService
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService

app = typer.Typer(
    help="Prompt Engine — compile CGS → provider packages (no media generation)",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("compile")
def compile_cmd(
    storyboard_id: str | None = typer.Option(None, "--storyboard", "-b"),
    shot_id: str | None = typer.Option(None, "--shot"),
    provider: str | None = typer.Option(None, "--provider", "-p"),
    modality: str = typer.Option("video", "--modality", "-m"),
    all_shots: bool = typer.Option(False, "--all"),
    experiment: bool = typer.Option(False, "--experiment"),
    bootstrap: bool = typer.Option(
        False, "--bootstrap", help="Create story+storyboard if no storyboard given"
    ),
    character: str | None = typer.Option(None, "--character", "-c"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    _init()
    with get_session() as session:
        svc = PromptService(session)
        if not storyboard_id and not shot_id:
            if not bootstrap:
                console.print("[red]Provide --storyboard or --bootstrap[/red]")
                raise typer.Exit(1)
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

        packages = svc.compile(
            CompileRequest(
                storyboard_id=storyboard_id,
                storyboard_shot_id=shot_id,
                provider=provider,
                modality=modality,  # type: ignore[arg-type]
                compile_all_shots=all_shots,
                experiment=experiment,
                fallback_providers=["runway"] if modality == "video" else [],
            )
        )

        if json_out:
            console.print_json(
                json.dumps(
                    [
                        {
                            "prompt_package_id": p.id,
                            "provider": p.provider,
                            "model": p.model,
                            "quality_score": float(p.quality_score or 0),
                            "estimated_cost": float(p.estimated_cost or 0),
                            "status": p.status,
                        }
                        for p in packages
                    ],
                    default=str,
                )
            )
            return

        table = Table(title=f"Prompt Packages ({len(packages)})")
        table.add_column("ID")
        table.add_column("Provider")
        table.add_column("Model")
        table.add_column("Quality")
        table.add_column("Cost")
        table.add_column("Status")
        for p in packages:
            table.add_row(
                p.id[:8],
                p.provider or "",
                p.model or "",
                f"{float(p.quality_score or 0):.3f}",
                f"{float(p.estimated_cost or 0):.3f}",
                p.status,
            )
        console.print(table)


@app.command("show")
def show_cmd(package_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        row = session.get(PromptPackage, package_id)
        if not row:
            rows = list(
                session.scalars(
                    select(PromptPackage).where(PromptPackage.id.startswith(package_id))
                ).all()
            )
            if len(rows) != 1:
                console.print("[red]Not found[/red]")
                raise typer.Exit(1)
            row = rows[0]
        console.print(
            Panel.fit(
                f"{row.provider}/{row.model} quality={float(row.quality_score or 0):.3f}",
                title=row.id,
            )
        )
        console.print_json(json.dumps(row.provider_prompt, default=str))


@app.command("spec")
def spec_cmd(spec_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        row = session.get(PromptSpec, spec_id)
        if not row:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        console.print_json(json.dumps(row.canonical_spec, default=str))


@app.command("providers")
def providers_cmd(modality: str | None = typer.Option(None, "--modality", "-m")) -> None:
    table = Table(title="Provider Registry")
    table.add_column("Name")
    table.add_column("Modalities")
    table.add_column("Model")
    for p in list_providers():
        mods = ",".join(p.get("modalities") or [])
        if modality and modality not in (p.get("modalities") or []):
            continue
        table.add_row(p["name"], mods, str((p.get("capabilities") or {}).get("model") or ""))
    console.print(table)
    if modality:
        ranked = rank_providers(modality)
        console.print("Ranking:", ", ".join(f"{n}={s}" for n, s in ranked))


@app.command("list")
def list_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    _init()
    with get_session() as session:
        rows = list(
            session.scalars(
                select(PromptPackage).order_by(PromptPackage.created_at.desc()).limit(limit)
            ).all()
        )
        table = Table(title="Recent Prompt Packages")
        table.add_column("ID")
        table.add_column("Provider")
        table.add_column("Modality")
        table.add_column("Quality")
        for p in rows:
            table.add_row(
                p.id[:8],
                p.provider or "",
                p.modality or "",
                f"{float(p.quality_score or 0):.3f}",
            )
        console.print(table)


if __name__ == "__main__":
    app()
