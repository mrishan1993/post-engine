from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import Prediction
from db.session import get_session, init_db, reset_engine
from prediction.calibration import calibration_report
from prediction.explainability import format_explanation
from prediction.learning import retrain_stub, self_improvement_kpis
from prediction.ranking import rank_briefs_for_production
from prediction.verification import verify_from_video_run, verify_prediction

app = typer.Typer(help="Probability & Verification Engine CLI", no_args_is_help=True)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("list")
def list_cmd(
    status: str = typer.Option("pending", "--status"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    _init()
    with get_session() as session:
        rows = session.scalars(
            select(Prediction)
            .where(Prediction.status == status)
            .order_by(Prediction.final_opportunity_score.desc())
            .limit(limit)
        ).all()
        table = Table(title=f"Predictions ({status})")
        table.add_column("ID")
        table.add_column("Vertical")
        table.add_column("Viral%")
        table.add_column("Views")
        table.add_column("Conf")
        table.add_column("Score")
        table.add_column("Brief")
        for p in rows:
            table.add_row(
                str(p.id),
                p.vertical_slug or "-",
                f"{float(p.virality_probability or 0):.0%}",
                f"{int(p.predicted_views or 0):,}",
                f"{float(p.confidence or 0):.0%}",
                f"{float(p.final_opportunity_score or 0):.1f}",
                str(p.content_brief_id or "-"),
            )
        console.print(table)


@app.command("show")
def show_cmd(prediction_id: int = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        p = session.get(Prediction, prediction_id)
        if not p:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        body = (
            f"Virality: {float(p.virality_probability or 0):.0%}\n"
            f"Expected views: {int(p.predicted_views or 0):,} "
            f"({int(p.predicted_views_low or 0):,}–{int(p.predicted_views_high or 0):,})\n"
            f"CTR: {float(p.predicted_ctr or 0):.1%} | Retention: {float(p.predicted_retention or 0):.0%}\n"
            f"Watch: {float(p.predicted_watch_time_sec or 0)}s | "
            f"Revenue: ${float(p.predicted_revenue_usd or 0):.2f} | ROI: {float(p.predicted_roi or 0):.1f}x\n"
            f"Confidence: {float(p.confidence or 0):.0%} | Risk: {float(p.risk_score or 0):.0%}\n"
            f"Final score: {float(p.final_opportunity_score or 0):.1f}\n"
            f"Model: {p.model_version} | Status: {p.status}\n\n"
            f"{format_explanation(p.reasoning_json or {})}"
        )
        console.print(Panel(body, title=f"Prediction #{p.id}"))


@app.command("verify")
def verify_cmd(
    prediction_id: int = typer.Argument(...),
    views: int = typer.Option(..., "--views"),
    comments: int = typer.Option(0, "--comments"),
    watch_time: float = typer.Option(0, "--watch-time"),
    revenue: float = typer.Option(0, "--revenue"),
    ctr: float = typer.Option(0.05, "--ctr"),
) -> None:
    """Manually verify a prediction against actuals."""
    _init()
    with get_session() as session:
        result = verify_prediction(
            session,
            prediction_id,
            {
                "views": views,
                "comments": comments,
                "watch_time_sec": watch_time,
                "revenue_usd": revenue,
                "ctr": ctr,
                "shares": int(views * 0.01),
                "saves": int(views * 0.008),
                "followers": int(views * 0.002),
                "retention": min(watch_time / 60.0, 1.0) if watch_time else None,
            },
        )
        console.print(
            f"[green]Verified[/green] prediction {prediction_id} MAPE={result.mape}\n"
            f"{(result.explanation or {}).get('lesson')}"
        )


@app.command("verify-run")
def verify_run_cmd(video_run_id: int = typer.Argument(...)) -> None:
    """Verify using metrics attached to a published video_run."""
    _init()
    with get_session() as session:
        result = verify_from_video_run(session, video_run_id)
        if not result:
            console.print("[yellow]No prediction/metrics found for that run[/yellow]")
            raise typer.Exit(1)
        console.print(f"[green]Verified[/green] prediction {result.prediction_id} MAPE={result.mape}")


@app.command("rank")
def rank_cmd(
    vertical: str | None = typer.Option(None, "--vertical", "-v"),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """Rank pending briefs by predicted opportunity score for production."""
    _init()
    with get_session() as session:
        ranked = rank_briefs_for_production(session, vertical_slug=vertical, limit=limit)
        table = Table(title="Production Queue (predicted)")
        table.add_column("Brief")
        table.add_column("Pred")
        table.add_column("Viral%")
        table.add_column("Views")
        table.add_column("Score")
        table.add_column("Snippet")
        for brief, pred in ranked:
            table.add_row(
                str(brief.id),
                str(pred.id),
                f"{float(pred.virality_probability or 0):.0%}",
                f"{int(pred.predicted_views or 0):,}",
                f"{float(pred.final_opportunity_score or 0):.1f}",
                (brief.brief_text or "").replace("\n", " ")[:50],
            )
        console.print(table)


@app.command("calibration")
def calibration_cmd() -> None:
    _init()
    with get_session() as session:
        console.print_json(json.dumps(calibration_report(session), default=str))


@app.command("kpis")
def kpis_cmd() -> None:
    _init()
    with get_session() as session:
        console.print_json(json.dumps(self_improvement_kpis(session), default=str))


@app.command("retrain")
def retrain_cmd() -> None:
    """Apply calibration multipliers (Phase 3 light)."""
    _init()
    with get_session() as session:
        console.print_json(json.dumps(retrain_stub(session), default=str))


if __name__ == "__main__":
    app()
