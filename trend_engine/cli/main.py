from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from db.models import ContentBrief, TrendScore, TrendTopic, Vertical
from db.session import get_session, init_db, reset_engine
from trend_engine.feedback.calibrator import suggest_weight_adjustments
from trend_engine.scheduler.daily_run import run_daily_ingestion

app = typer.Typer(help="Trend engine — ingest signals and feed content_briefs", no_args_is_help=True)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("ingest")
def ingest_cmd() -> None:
    """Run daily collectors → normalize → score → write content_briefs."""
    _init()
    with get_session() as session:
        result = run_daily_ingestion(session)
        console.print(
            f"[green]Ingest complete[/green] signals={result.signals_collected} "
            f"topics={result.topics_created} briefs={result.briefs_created}"
        )
        if result.per_vertical_candidates:
            table = Table(title="Candidates by vertical")
            table.add_column("Vertical")
            table.add_column("Topics")
            for slug, n in sorted(result.per_vertical_candidates.items()):
                table.add_row(slug, str(n))
            console.print(table)


@app.command("topics")
def topics_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    """List recent scored topics."""
    _init()
    with get_session() as session:
        topics = session.scalars(
            select(TrendTopic).order_by(TrendTopic.last_seen_at.desc()).limit(limit)
        ).all()
        table = Table(title="Trend Topics")
        table.add_column("ID")
        table.add_column("Label")
        table.add_column("Score")
        table.add_column("Verticals")
        table.add_column("Status")
        for topic in topics:
            latest = session.scalar(
                select(TrendScore)
                .where(TrendScore.topic_id == topic.id)
                .order_by(TrendScore.scored_at.desc())
                .limit(1)
            )
            table.add_row(
                str(topic.id),
                (topic.topic_label or "")[:48],
                f"{float(latest.score):.3f}" if latest else "-",
                ",".join(topic.candidate_verticals or []),
                topic.status,
            )
        console.print(table)


@app.command("briefs")
def briefs_cmd() -> None:
    """Show pending briefs created by the trend engine."""
    _init()
    with get_session() as session:
        rows = session.execute(
            select(ContentBrief, Vertical)
            .join(Vertical, Vertical.id == ContentBrief.vertical_id)
            .where(ContentBrief.source == "trend_engine")
            .order_by(ContentBrief.priority.desc(), ContentBrief.created_at.desc())
        ).all()
        table = Table(title="Trend-sourced Briefs")
        table.add_column("ID")
        table.add_column("Vertical")
        table.add_column("Priority")
        table.add_column("Status")
        table.add_column("Brief")
        for brief, vertical in rows:
            table.add_row(
                str(brief.id),
                vertical.slug,
                str(brief.priority),
                brief.status,
                (brief.brief_text or "")[:60],
            )
        console.print(table)


@app.command("calibrate")
def calibrate_cmd() -> None:
    """Print feedback-based weight tuning suggestions (manual review)."""
    _init()
    with get_session() as session:
        suggestion = suggest_weight_adjustments(session)
        console.print(suggestion)


if __name__ == "__main__":
    app()
