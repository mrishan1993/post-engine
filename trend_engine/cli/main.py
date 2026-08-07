from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import ContentBrief, OpportunityScore, TrendScore, TrendTopic, Vertical
from db.session import get_session, init_db, reset_engine
from trend_engine.feedback.calibrator import suggest_weight_adjustments
from trend_engine.scheduler.daily_run import run_daily_ingestion
from trend_engine.v2.pipeline import answer_what_to_make, run_v2_intelligence

app = typer.Typer(help="Trend engine — V1 topics + V2 viral opportunities", no_args_is_help=True)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("ingest")
def ingest_cmd() -> None:
    """V1: collectors → topic score → content_briefs (source=trend_engine)."""
    _init()
    with get_session() as session:
        result = run_daily_ingestion(session)
        console.print(
            f"[green]V1 ingest complete[/green] signals={result.signals_collected} "
            f"topics={result.topics_created} briefs={result.briefs_created}"
        )


@app.command("v2")
def v2_cmd(
    vertical: str | None = typer.Option(None, "--vertical", "-v", help="Limit to one vertical"),
) -> None:
    """V2: Content DNA → opportunities → character-adapted briefs (next 12h)."""
    _init()
    with get_session() as session:
        result = run_v2_intelligence(session, vertical=vertical)
        console.print(
            f"[green]V2 complete[/green] raw={result.raw_content} features={result.features} "
            f"opportunities={result.opportunities} briefs={result.briefs} "
            f"graph_edges={result.graph_edges}"
        )


@app.command("what-next")
def what_next_cmd(
    vertical: str = typer.Option(..., "--vertical", "-v"),
    limit: int = typer.Option(5, "--limit"),
) -> None:
    """Answer: if we publish in the next 12 hours, what should we make?"""
    _init()
    with get_session() as session:
        # Ensure we have fresh opportunities
        run_v2_intelligence(session, vertical=vertical)
        opps = answer_what_to_make(session, vertical, limit=limit)
        if not opps:
            console.print("[yellow]No active opportunities. Try `trend v2` first.[/yellow]")
            raise typer.Exit(1)
        for opp in opps:
            payload = opp.opportunity or {}
            body = (
                f"[bold]Score:[/bold] {float(opp.score):.0f}/100\n"
                f"[bold]Trend:[/bold] {payload.get('trend')}\n"
                f"[bold]Lifecycle:[/bold] {opp.lifecycle_stage}\n"
                f"[bold]Platforms:[/bold] {', '.join(payload.get('platforms') or [])}\n"
                f"[bold]Emotion:[/bold] {payload.get('emotion')}\n"
                f"[bold]Hook:[/bold] {payload.get('hook')}\n"
                f"[bold]Story:[/bold] {payload.get('story_pattern')} | "
                f"[bold]Audio:[/bold] {payload.get('audio')} | "
                f"[bold]Edit:[/bold] {payload.get('editing_style')}\n"
                f"[bold]Audience:[/bold] {payload.get('target_audience')}\n"
                f"[bold]Characters:[/bold] {', '.join(payload.get('suggested_characters') or [])}\n"
                f"[bold]Why:[/bold]\n- " + "\n- ".join(payload.get("why_viral") or [])
            )
            console.print(Panel(body, title=f"Opportunity #{opp.id}", expand=False))


@app.command("opportunities")
def opportunities_cmd(
    vertical: str | None = typer.Option(None, "--vertical", "-v"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """List ranked viral opportunities."""
    _init()
    with get_session() as session:
        q = select(OpportunityScore).order_by(OpportunityScore.score.desc()).limit(limit)
        if vertical:
            q = (
                select(OpportunityScore)
                .where(OpportunityScore.vertical_slug == vertical)
                .order_by(OpportunityScore.score.desc())
                .limit(limit)
            )
        rows = session.scalars(q).all()
        table = Table(title="Viral Opportunities")
        table.add_column("ID")
        table.add_column("Vertical")
        table.add_column("Score")
        table.add_column("Lifecycle")
        table.add_column("Title")
        for row in rows:
            table.add_row(
                str(row.id),
                row.vertical_slug,
                f"{float(row.score):.1f}",
                row.lifecycle_stage or "-",
                row.title[:48],
            )
        console.print(table)


@app.command("topics")
def topics_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    """V1: list recent scored topics."""
    _init()
    with get_session() as session:
        topics = session.scalars(
            select(TrendTopic).order_by(TrendTopic.last_seen_at.desc()).limit(limit)
        ).all()
        table = Table(title="Trend Topics (V1)")
        table.add_column("ID")
        table.add_column("Label")
        table.add_column("Score")
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
                topic.status,
            )
        console.print(table)


@app.command("briefs")
def briefs_cmd(
    source: str = typer.Option("trend_engine_v2", "--source", help="trend_engine | trend_engine_v2 | all"),
) -> None:
    """Show pending briefs from the trend engine."""
    _init()
    with get_session() as session:
        q = (
            select(ContentBrief, Vertical)
            .join(Vertical, Vertical.id == ContentBrief.vertical_id)
            .order_by(ContentBrief.priority.desc(), ContentBrief.created_at.desc())
        )
        if source != "all":
            q = q.where(ContentBrief.source == source)
        else:
            q = q.where(ContentBrief.source.in_(["trend_engine", "trend_engine_v2"]))
        rows = session.execute(q).all()
        table = Table(title="Trend Briefs")
        table.add_column("ID")
        table.add_column("Src")
        table.add_column("Vertical")
        table.add_column("Pri")
        table.add_column("Brief")
        for brief, vertical in rows:
            table.add_row(
                str(brief.id),
                (brief.source or "")[-6:],
                vertical.slug,
                str(brief.priority),
                (brief.brief_text or "").replace("\n", " ")[:70],
            )
        console.print(table)


@app.command("show-opportunity")
def show_opportunity_cmd(opportunity_id: int = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        row = session.get(OpportunityScore, opportunity_id)
        if not row:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        console.print_json(json.dumps(row.opportunity or {}, default=str))


@app.command("calibrate")
def calibrate_cmd() -> None:
    """V1 feedback weight suggestions."""
    _init()
    with get_session() as session:
        console.print(suggest_weight_adjustments(session))


if __name__ == "__main__":
    app()
