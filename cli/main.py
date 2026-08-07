from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from db.session import get_session, init_db, reset_engine
from orchestration.pipeline import Pipeline
from qa.review_queue import list_pending_reviews
from qa.safety_checks import summarize_flags

app = typer.Typer(help="Automated AI content pipeline CLI", no_args_is_help=True)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("run")
def run_cmd(
    vertical: str = typer.Option(..., "--vertical", "-v", help="Vertical slug"),
    brief: str = typer.Option(..., "--brief", "-b", help="Content brief text"),
    priority: int = typer.Option(0, "--priority"),
) -> None:
    """Create a brief + video_run and execute through qa_pending."""
    _init()
    with get_session() as session:
        pipeline = Pipeline(session)
        row = pipeline.enqueue_brief(vertical, brief, priority=priority, source="manual")
        video_run = pipeline.create_run(row)
        console.print(f"Created video_run [bold]{video_run.id}[/bold], running…")
        pipeline.run_until_qa(video_run.id)
        console.print(
            f"[green]Done[/green] → status={video_run.status} "
            f"path={video_run.rendered_video_path} cost=${float(video_run.total_cost_usd):.4f}"
        )


@app.command("review")
def review_cmd() -> None:
    """List videos waiting in qa_pending."""
    _init()
    with get_session() as session:
        items = list_pending_reviews(session)
        table = Table(title="QA Review Queue")
        table.add_column("ID")
        table.add_column("Title")
        table.add_column("Vertical")
        table.add_column("Flags")
        if not items:
            console.print("[dim]No videos in qa_pending[/dim]")
            return
        for item in items:
            flags = (
                ", ".join(f"{k}: {v:.2f}" for k, v in item.flags.items())
                if item.flags
                else "none"
            )
            table.add_row(str(item.id), item.title, item.vertical, flags)
        console.print(table)


@app.command("preview")
def preview_cmd(run_id: int = typer.Argument(...)) -> None:
    """Open rendered video in the default player."""
    _init()
    with get_session() as session:
        from db.models import VideoRun

        run = session.get(VideoRun, run_id)
        if not run or not run.rendered_video_path:
            console.print("[red]No rendered video for that run[/red]")
            raise typer.Exit(1)
        path = Path(run.rendered_video_path)
        if not path.exists():
            console.print(f"[red]Missing file:[/red] {path}")
            raise typer.Exit(1)
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(path)], check=False)
        else:
            console.print(path)


@app.command("approve")
def approve_cmd(
    run_id: int = typer.Argument(...),
    reviewer: str = typer.Option(..., "--reviewer"),
    publish: bool = typer.Option(False, "--publish", help="Publish immediately after approve"),
) -> None:
    _init()
    with get_session() as session:
        pipeline = Pipeline(session)
        run = pipeline.approve(run_id, reviewer=reviewer)
        console.print(f"[green]Approved[/green] run {run.id}")
        if publish:
            run = pipeline.publish(run.id)
            console.print(f"[green]Published[/green] run {run.id}")


@app.command("reject")
def reject_cmd(
    run_id: int = typer.Argument(...),
    reviewer: str = typer.Option(..., "--reviewer"),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    _init()
    with get_session() as session:
        pipeline = Pipeline(session)
        run = pipeline.reject(run_id, reviewer=reviewer, reason=reason)
        console.print(f"[yellow]Rejected[/yellow] run {run.id}: {run.qa_notes}")


@app.command("regen")
def regen_cmd(
    run_id: int = typer.Argument(...),
    from_status: str = typer.Option(
        "audio_done",
        "--from",
        help="Resume status: created|script_done|audio_done|visual_done|assembled",
    ),
    execute: bool = typer.Option(True, "--execute/--no-execute"),
) -> None:
    """Create a child run from a rejected parent and optionally continue the pipeline."""
    _init()
    with get_session() as session:
        pipeline = Pipeline(session)
        child = pipeline.regen(run_id, from_status=from_status)
        console.print(f"Created child run [bold]{child.id}[/bold] at status={child.status}")
        if execute:
            pipeline.run_until_qa(child.id)
            console.print(f"[green]Child at[/green] {child.status}")


@app.command("publish")
def publish_cmd(run_id: int = typer.Argument(...)) -> None:
    """Publish a qa_approved run (never bypasses QA)."""
    _init()
    with get_session() as session:
        pipeline = Pipeline(session)
        run = pipeline.publish(run_id)
        console.print(f"[green]Published[/green] run {run.id}")


@app.command("show")
def show_cmd(run_id: int = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        from db.models import VideoRun

        run = session.get(VideoRun, run_id)
        if not run:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        console.print(
            {
                "id": run.id,
                "status": run.status,
                "title": run.title,
                "cost_usd": float(run.total_cost_usd or 0),
                "rendered_video_path": run.rendered_video_path,
                "flags": summarize_flags(run.safety_check_result),
                "qa_reviewer": run.qa_reviewer,
                "qa_notes": run.qa_notes,
                "error_log": run.error_log,
            }
        )


@app.command("init-db")
def init_db_cmd() -> None:
    _init()
    console.print("[green]Database initialized[/green]")


if __name__ == "__main__":
    app()
