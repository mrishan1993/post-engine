from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from db.session import get_session, init_db, reset_engine
from strategy_engine.schemas import (
    CreatePlanRequest,
    CreateStrategyRequest,
    ExecuteRequest,
    IngestOpportunityRequest,
    ReplanRequest,
    StrategyProfile,
)
from strategy_engine.service import StrategyService

app = typer.Typer(
    help="Content Strategy & Planning — portfolio, calendar, replan, execute",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str = typer.Option("ghost_kid", "--character", "-c"),
    execute: bool = typer.Option(False, "--execute"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Bootstrap strategy → opportunities → plan (+ optional orchestrator handoff)."""
    _init()
    with get_session() as session:
        if not bootstrap:
            console.print("[red]Use --bootstrap[/red]")
            raise typer.Exit(1)
        svc = StrategyService(session)
        strategy = svc.create_strategy(
            CreateStrategyRequest(
                name="growth_60d",
                character_slug=character,
                profile=StrategyProfile(),
                autonomy="semi_autonomous",
            )
        )
        # Seed mix of opportunities
        seeds = [
            ("trend", "Unexpected reveal accelerating", "trend", 0.91, 0.2, 12),
            ("trend", "Secondary dance format", "trend", 0.7, 0.4, 36),
            ("evergreen", "Character morning routine", "character", 0.55, 0.1, None),
            ("evergreen", "How suspense hooks work", "education", 0.5, 0.1, None),
            ("experiment", "3s vs 6s hook test", "experiment", 0.45, 0.2, 168),
            ("evergreen", "Community Q&A tease", "character", 0.48, 0.1, None),
            ("campaign", "Launch week awareness", "evergreen", 0.6, 0.15, 72),
            ("gap", "Fill education debt", "education", 0.42, 0.1, None),
        ]
        for source, title, pillar, score, sat, exp_h in seeds:
            svc.ingest_opportunity(
                IngestOpportunityRequest(
                    strategy_id=strategy.strategy_id,
                    source=source,  # type: ignore[arg-type]
                    title=title,
                    pillar=pillar,
                    platform="instagram",
                    payload={
                        "opportunity_score": score,
                        "velocity_score": score,
                        "freshness_score": 0.85 if source == "trend" else 0.6,
                        "saturation_score": sat,
                        "viral_mechanism": "unexpected_reveal" if "reveal" in title.lower() else "curiosity_gap",
                        "trend_stage": "accelerating" if source == "trend" else "evergreen",
                    },
                    expiration_hours=exp_h,
                    trend_id=f"trend_{title[:8].replace(' ', '_').lower()}",
                )
            )
        plan = svc.create_plan(CreatePlanRequest(strategy_id=strategy.strategy_id, days=7))
        exec_out = []
        if execute:
            exec_out = svc.execute(
                ExecuteRequest(
                    strategy_id=strategy.strategy_id,
                    plan_id=plan.plan_id,
                    max_jobs=1,
                    run_pipeline=False,
                )
            )
        if json_out:
            console.print_json(
                data={
                    "strategy": strategy.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json"),
                    "execution": exec_out,
                }
            )
            return
        console.print(
            Panel(
                f"strategy={strategy.strategy_id}\n"
                f"plan={plan.plan_id} v{plan.version} items={len(plan.items)}\n"
                f"mix={plan.content_mix}\n"
                f"debt={plan.content_debt}\n"
                f"warnings={plan.warnings}\n"
                f"execution={exec_out}",
                title="Content Plan",
            )
        )
        table = Table(title="Calendar")
        table.add_column("When")
        table.add_column("Pillar")
        table.add_column("Priority")
        table.add_column("Title")
        for it in plan.items:
            table.add_row(
                it.scheduled_at.isoformat() if it.scheduled_at else "",
                it.pillar or "",
                it.priority,
                it.title or "",
            )
        console.print(table)


@app.command("show")
def show_cmd(strategy_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=StrategyService(session).get_strategy(strategy_id).model_dump(mode="json"))


@app.command("opportunities")
def opportunities_cmd(strategy_id: str, status: str | None = typer.Option(None, "--status")) -> None:
    _init()
    with get_session() as session:
        rows = StrategyService(session).list_opportunities(strategy_id, status=status)
        table = Table(title="Opportunities")
        table.add_column("ID")
        table.add_column("Source")
        table.add_column("Score")
        table.add_column("Pri")
        table.add_column("Status")
        table.add_column("Title")
        for r in rows:
            table.add_row(
                r.opportunity_id[:8],
                r.source,
                f"{r.strategic_score or 0:.2f}",
                r.priority,
                r.status,
                r.title or "",
            )
        console.print(table)


@app.command("plan")
def plan_cmd(strategy_id: str, days: int = typer.Option(7, "--days")) -> None:
    _init()
    with get_session() as session:
        out = StrategyService(session).create_plan(
            CreatePlanRequest(strategy_id=strategy_id, days=days)
        )
        console.print_json(data=out.model_dump(mode="json"))


@app.command("calendar")
def calendar_cmd(strategy_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=StrategyService(session).calendar(strategy_id))


@app.command("replan")
def replan_cmd(
    plan_id: str,
    trend: str | None = typer.Option(None, "--trend", help="opportunity or trend id to force-insert"),
) -> None:
    _init()
    with get_session() as session:
        out = StrategyService(session).replan(
            ReplanRequest(plan_id=plan_id, force_trend_id=trend, reason="cli replan")
        )
        console.print_json(data=out.model_dump(mode="json"))


@app.command("execute")
def execute_cmd(
    strategy_id: str,
    max_jobs: int = typer.Option(1, "--max"),
    pipeline: bool = typer.Option(False, "--pipeline"),
) -> None:
    _init()
    with get_session() as session:
        out = StrategyService(session).execute(
            ExecuteRequest(
                strategy_id=strategy_id,
                max_jobs=max_jobs,
                run_pipeline=pipeline,
            )
        )
        console.print_json(data=out)


@app.command("decisions")
def decisions_cmd(strategy_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=StrategyService(session).decisions(strategy_id))


@app.command("health")
def health_cmd(strategy_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=StrategyService(session).health(strategy_id))


@app.command("pause")
def pause_cmd(strategy_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=StrategyService(session).pause(strategy_id).model_dump(mode="json"))
