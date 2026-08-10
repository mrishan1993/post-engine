from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import NarrativePattern, Story
from db.session import get_session, init_db, reset_engine
from story_engine.patterns import ensure_default_patterns
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService

app = typer.Typer(help="Story Engine — narrative blueprints (not video)", no_args_is_help=True)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("generate")
def generate_cmd(
    topic: str = typer.Option("POV horror", "--topic", "-t"),
    emotion: str = typer.Option("fear", "--emotion", "-e"),
    platform: str = typer.Option("instagram_reels", "--platform", "-p"),
    duration: int = typer.Option(30, "--duration", "-d"),
    format_: str = typer.Option("POV", "--format", "-f"),
    story_type: str = typer.Option("pov_horror", "--type"),
    character: str | None = typer.Option(None, "--character", "-c", help="Character slug"),
    candidates: int = typer.Option(3, "--candidates", "-n"),
    approve_winner: bool = typer.Option(False, "--approve-winner"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Generate story blueprint candidates from opportunity + creative direction."""
    _init()
    req: dict[str, Any] = {
        "content_opportunity": {
            "topic": topic,
            "emotion": emotion,
            "platform": platform,
            "trend_score": 80,
            "trend_stage": "growing",
        },
        "creative_direction": {
            "format": format_,
            "target_duration_sec": duration,
            "pacing": "fast",
        },
        "story_type": story_type,
        "candidate_count": candidates,
        "max_revisions": 2,
        "characters": [{"character_slug": character, "role": "protagonist"}]
        if character
        else [],
    }
    with get_session() as session:
        stories = StoryService(session).generate(StoryRequest.model_validate(req))
        winner = None
        if approve_winner and stories:
            winner = StoryService(session).select_winner(stories)
        if json_out:
            console.print_json(
                json.dumps(
                    {
                        "stories": [
                            {
                                "story_id": s.id,
                                "title": s.title,
                                "quality_score": float(s.quality_score or 0),
                                "status": s.status,
                            }
                            for s in stories
                        ],
                        "winner_id": winner.id if winner else None,
                    },
                    default=str,
                )
            )
            return
        table = Table(title="Story Candidates")
        table.add_column("ID", style="dim")
        table.add_column("Title")
        table.add_column("Quality")
        table.add_column("Status")
        for s in stories:
            table.add_row(
                s.id[:8],
                s.title or "",
                f"{float(s.quality_score or 0):.3f}",
                s.status,
            )
        console.print(table)
        if winner:
            console.print(f"[green]Winner approved:[/green] {winner.id} — {winner.title}")


@app.command("show")
def show_cmd(story_id: str = typer.Argument(...)) -> None:
    """Print a story blueprint as JSON."""
    _init()
    with get_session() as session:
        story = session.get(Story, story_id)
        if not story:
            # allow short prefix
            rows = list(
                session.scalars(select(Story).where(Story.id.startswith(story_id))).all()
            )
            if len(rows) != 1:
                console.print("[red]Story not found[/red]")
                raise typer.Exit(1)
            story = rows[0]
        console.print(
            Panel.fit(
                f"[bold]{story.title}[/bold]\n{story.logline}\n"
                f"quality={float(story.quality_score or 0):.3f} status={story.status}",
                title=story.id,
            )
        )
        console.print_json(json.dumps(story.blueprint, default=str))


@app.command("list")
def list_cmd(
    status: str | None = typer.Option(None, "--status"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    _init()
    with get_session() as session:
        q = select(Story).order_by(Story.created_at.desc()).limit(limit)
        if status:
            q = q.where(Story.status == status)
        rows = list(session.scalars(q).all())
        table = Table(title="Stories")
        table.add_column("ID")
        table.add_column("Title")
        table.add_column("Quality")
        table.add_column("Status")
        table.add_column("Platform")
        for s in rows:
            table.add_row(
                s.id[:8],
                (s.title or "")[:40],
                f"{float(s.quality_score or 0):.3f}",
                s.status,
                s.platform or "",
            )
        console.print(table)


@app.command("revise")
def revise_cmd(story_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        story = StoryService(session).revise(story_id)
        console.print(
            f"[green]Revised[/green] v{story.current_version} "
            f"quality={float(story.quality_score or 0):.3f}"
        )


@app.command("approve")
def approve_cmd(story_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        story = StoryService(session).approve(story_id)
        console.print(f"[green]Approved[/green] {story.id}")


@app.command("compare")
def compare_cmd(ids: list[str] = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        rows = StoryService(session).compare(ids)
        for i, s in enumerate(rows, 1):
            console.print(
                f"{i}. {s.id[:8]}  {float(s.quality_score or 0):.3f}  {s.title}"
            )


@app.command("patterns")
def patterns_cmd(seed: bool = typer.Option(False, "--seed")) -> None:
    """List narrative patterns (Story Engine library)."""
    _init()
    with get_session() as session:
        if seed:
            n = ensure_default_patterns(session)
            console.print(f"[green]Seeded[/green] {n} patterns")
        rows = list(session.scalars(select(NarrativePattern).order_by(NarrativePattern.name)).all())
        table = Table(title="Narrative Patterns")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Structure")
        for p in rows:
            table.add_row(
                p.name,
                p.pattern_type or "",
                json.dumps(p.structure)[:60],
            )
        console.print(table)


if __name__ == "__main__":
    app()
