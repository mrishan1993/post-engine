from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import Story, Storyboard, StoryboardScene, StoryboardShot
from db.session import get_session, init_db, reset_engine
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService

app = typer.Typer(
    help="Storyboard Engine — visual/audio specs (not generation/prompts)",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


def _resolve_story_id(session, story_id: str) -> Story:
    story = session.get(Story, story_id)
    if story:
        return story
    rows = list(session.scalars(select(Story).where(Story.id.startswith(story_id))).all())
    if len(rows) != 1:
        console.print("[red]Story not found[/red]")
        raise typer.Exit(1)
    return rows[0]


@app.command("generate")
def generate_cmd(
    story_id: str | None = typer.Option(None, "--story", "-s", help="Existing story id"),
    topic: str = typer.Option("POV horror", "--topic", "-t"),
    character: str | None = typer.Option(None, "--character", "-c"),
    platform: str = typer.Option("instagram_reels", "--platform", "-p"),
    duration: int = typer.Option(30, "--duration", "-d"),
    approve: bool = typer.Option(False, "--approve"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Generate a storyboard from a story (creates a story first if --story omitted)."""
    _init()
    with get_session() as session:
        if story_id:
            story = _resolve_story_id(session, story_id)
        else:
            stories = StoryService(session).generate(
                StoryRequest.model_validate(
                    {
                        "content_opportunity": {
                            "topic": topic,
                            "emotion": "fear",
                            "platform": platform,
                            "trend_score": 85,
                        },
                        "creative_direction": {
                            "format": "POV",
                            "target_duration_sec": duration,
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
            story = stories[0]
            console.print(f"[dim]Created story[/dim] {story.id[:8]} — {story.title}")

        board = StoryboardService(session).generate(
            StoryboardRequest(
                story_id=story.id,
                platform=platform,
                character_slugs=[character] if character else [],
                target_duration_sec=duration,
                location_query="Haunted School" if "horror" in topic.lower() else None,
            )
        )
        if approve:
            board = StoryboardService(session).approve(board.id)

        doc = board.document or {}
        scene_count = len(doc.get("scenes") or [])
        shot_count = sum(len(s.get("shots") or []) for s in doc.get("scenes") or [])

        if json_out:
            console.print_json(
                json.dumps(
                    {
                        "storyboard_id": board.id,
                        "story_id": board.story_id,
                        "version": board.version,
                        "scene_count": scene_count,
                        "shot_count": shot_count,
                        "duration_sec": float(board.duration_sec or 0),
                        "quality_score": float(board.quality_score or 0),
                        "status": board.status,
                    },
                    default=str,
                )
            )
            return

        console.print(
            Panel.fit(
                f"[bold]{doc.get('title') or story.title}[/bold]\n"
                f"scenes={scene_count} shots={shot_count} "
                f"duration={float(board.duration_sec or 0):.1f}s "
                f"quality={float(board.quality_score or 0):.3f}\n"
                f"status={board.status} v{board.version}",
                title=board.id,
            )
        )


@app.command("show")
def show_cmd(storyboard_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        board = session.get(Storyboard, storyboard_id)
        if not board:
            rows = list(
                session.scalars(
                    select(Storyboard).where(Storyboard.id.startswith(storyboard_id))
                ).all()
            )
            if len(rows) != 1:
                console.print("[red]Not found[/red]")
                raise typer.Exit(1)
            board = rows[0]
        console.print_json(json.dumps(board.document, default=str))


@app.command("list")
def list_cmd(
    story_id: str | None = typer.Option(None, "--story", "-s"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    _init()
    with get_session() as session:
        q = select(Storyboard).order_by(Storyboard.created_at.desc()).limit(limit)
        if story_id:
            story = _resolve_story_id(session, story_id)
            q = (
                select(Storyboard)
                .where(Storyboard.story_id == story.id)
                .order_by(Storyboard.version.desc())
                .limit(limit)
            )
        rows = list(session.scalars(q).all())
        table = Table(title="Storyboards")
        table.add_column("ID")
        table.add_column("Story")
        table.add_column("Ver")
        table.add_column("Quality")
        table.add_column("Status")
        table.add_column("Dur")
        for b in rows:
            table.add_row(
                b.id[:8],
                (b.story_id or "")[:8],
                str(b.version),
                f"{float(b.quality_score or 0):.3f}",
                b.status,
                f"{float(b.duration_sec or 0):.1f}",
            )
        console.print(table)


@app.command("scenes")
def scenes_cmd(storyboard_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        board = session.get(Storyboard, storyboard_id)
        if not board:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        rows = list(
            session.scalars(
                select(StoryboardScene)
                .where(StoryboardScene.storyboard_id == board.id)
                .order_by(StoryboardScene.sequence_number)
            ).all()
        )
        table = Table(title=f"Scenes — {board.id[:8]}")
        table.add_column("#")
        table.add_column("Function")
        table.add_column("Start")
        table.add_column("End")
        table.add_column("Shots")
        for sc in rows:
            shots = list(
                session.scalars(
                    select(StoryboardShot).where(StoryboardShot.scene_id == sc.id)
                ).all()
            )
            table.add_row(
                str(sc.sequence_number),
                sc.narrative_function or "",
                f"{float(sc.start_time_sec or 0):.1f}",
                f"{float(sc.end_time_sec or 0):.1f}",
                str(len(shots)),
            )
        console.print(table)


@app.command("revise")
def revise_cmd(storyboard_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        board = StoryboardService(session).revise(storyboard_id)
        console.print(
            f"[green]Revised[/green] → {board.id[:8]} v{board.version} "
            f"quality={float(board.quality_score or 0):.3f}"
        )


@app.command("approve")
def approve_cmd(storyboard_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        board = StoryboardService(session).approve(storyboard_id)
        console.print(f"[green]Approved[/green] {board.id}")


if __name__ == "__main__":
    app()
