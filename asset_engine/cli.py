from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from asset_engine.characters import CharacterRegistry
from asset_engine.registry import AssetRegistry
from asset_engine.resolver import resolve_generation_context
from asset_engine.schemas import SceneRequest
from asset_engine.seed import seed_from_v2_config
from db.session import get_session, init_db, reset_engine

app = typer.Typer(help="Asset & Character Management Engine (AMP)", no_args_is_help=True)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("seed")
def seed_cmd() -> None:
    """Seed characters/styles/locations from trend v2 config + kids rig assets."""
    _init()
    with get_session() as session:
        result = seed_from_v2_config(session)
        console.print(f"[green]Seeded[/green] {result}")


@app.command("characters")
def characters_cmd(status: str | None = typer.Option(None, "--status")) -> None:
    _init()
    with get_session() as session:
        rows = CharacterRegistry(session).list_characters(status=status)
        table = Table(title="Characters")
        table.add_column("Slug")
        table.add_column("Name")
        table.add_column("Ver")
        table.add_column("Status")
        table.add_column("Tags")
        for c in rows:
            table.add_row(
                c.slug,
                c.name,
                str(c.current_version),
                c.status,
                ",".join(c.tags or [])[:40],
            )
        console.print(table)


@app.command("show-character")
def show_character_cmd(slug: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        char = CharacterRegistry(session).by_slug(slug)
        if not char:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        console.print_json(
            json.dumps(
                {
                    "id": char.id,
                    "slug": char.slug,
                    "name": char.name,
                    "version": char.current_version,
                    "status": char.status,
                    "canonical_data": char.canonical_data,
                },
                default=str,
            )
        )


@app.command("assets")
def assets_cmd(
    asset_type: str | None = typer.Option(None, "--type"),
    query: str | None = typer.Option(None, "--query", "-q"),
) -> None:
    _init()
    with get_session() as session:
        rows = AssetRegistry(session).search(query=query, asset_type=asset_type, limit=40)
        table = Table(title="Assets")
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Provider")
        for a in rows:
            table.add_row(a.id[:8], a.asset_type, (a.name or "")[:28], a.status, a.provider or "-")
        console.print(table)


@app.command("resolve")
def resolve_cmd(
    character: str = typer.Option(..., "--character", "-c"),
    location: str | None = typer.Option(None, "--location"),
    emotion: str | None = typer.Option(None, "--emotion"),
    action: str | None = typer.Option(None, "--action"),
    prop: str | None = typer.Option(None, "--prop"),
    style: str | None = typer.Option(None, "--style"),
    platform: str = typer.Option("youtube_shorts", "--platform"),
) -> None:
    """Resolve a full generation context for a scene."""
    _init()
    with get_session() as session:
        ctx = resolve_generation_context(
            session,
            SceneRequest(
                character_slug=character,
                location=location,
                emotion=emotion,
                action=action,
                prop=prop,
                style=style,
                platform=platform,
            ),
        )
        console.print(
            Panel(
                f"[bold]{ctx.character.get('name')}[/bold] v{ctx.character.get('version')}\n"
                f"Refs: {len(ctx.references)} | "
                f"Location: {(ctx.location or {}).get('name') or '-'} | "
                f"Style: {(ctx.style or {}).get('slug') or '-'} | "
                f"Voice: {(ctx.voice or {}).get('slug') or '-'}\n"
                f"Memory beats: {len(ctx.memory)}\n"
                f"Canon immutable: {', '.join(ctx.constraints.get('immutable') or [])}",
                title="Generation Context",
            )
        )
        console.print_json(ctx.model_dump_json())


@app.command("memory")
def memory_cmd(
    character: str = typer.Argument(...),
    episode: str | None = typer.Option(None, "--episode"),
    text: str | None = typer.Option(None, "--text"),
) -> None:
    """List or append character story memory."""
    _init()
    with get_session() as session:
        reg = CharacterRegistry(session)
        char = reg.by_slug(character)
        if not char:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        if episode and text:
            reg.add_memory(char.id, episode_key=episode, memory_text=text)
            console.print("[green]Memory added[/green]")
        for m in reg.memories(char.id):
            console.print(f"- [{m.episode_key}] {m.memory_text}")


if __name__ == "__main__":
    app()
