from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from db.session import get_session, init_db, reset_engine
from orchestration_engine.schemas import ApproveJobRequest, CreateJobRequest, TrendOpportunityIn
from orchestration_engine.service import OrchestrationService

app = typer.Typer(
    help="Trend-to-Reel Orchestration — evaluate → concept → brief → produce → publish",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


def _demo_opportunity(**overrides) -> TrendOpportunityIn:
    base = dict(
        trend_id="trend_demo_001",
        platform="instagram",
        trend_stage="accelerating",
        velocity_score=0.91,
        freshness_score=0.88,
        saturation_score=0.24,
        opportunity_score=0.91,
        viral_mechanism="unexpected_reveal",
        format="short_form_video",
        title="Unexpected reveal format accelerating",
        audience=["gen_z", "millennials"],
    )
    base.update(overrides)
    return TrendOpportunityIn.model_validate(base)


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str = typer.Option("ghost_kid", "--character", "-c"),
    mode: str = typer.Option("autonomous", "--mode"),
    pipeline: bool = typer.Option(True, "--pipeline/--brief-only"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Bootstrap a trend opportunity through orchestration."""
    _init()
    with get_session() as session:
        if bootstrap and pipeline:
            from asset_engine.seed import seed_from_v2_config

            seed_from_v2_config(session)

        if not bootstrap:
            console.print("[red]Use --bootstrap[/red]")
            raise typer.Exit(1)

        out = OrchestrationService(session).create_job(
            CreateJobRequest(
                opportunity=_demo_opportunity(),
                character_slug=character,
                mode=mode,  # type: ignore[arg-type]
                process=True,
                run_pipeline=pipeline,
            )
        )
        if json_out:
            console.print_json(data=out.model_dump(mode="json"))
            return

        console.print(
            Panel(
                f"job={out.job_id}\n"
                f"status={out.status} stage={out.current_stage}\n"
                f"actionability={out.actionability} priority={out.priority}\n"
                f"selected={out.selected_concept_id} backup={out.backup_concept_id}\n"
                f"brief={out.production_brief_id}\n"
                f"gate={out.approval_gate}\n"
                f"lineage_keys={list((out.lineage or {}).keys())}",
                title="Orchestration Job",
            )
        )
        if out.concepts:
            table = Table(title="Concepts")
            table.add_column("ID")
            table.add_column("Angle")
            table.add_column("Score")
            table.add_column("Flag")
            for c in sorted(out.concepts, key=lambda x: -(x.score or 0)):
                flag = "PRIMARY" if c.selected else ("BACKUP" if c.is_backup else "")
                table.add_row(c.concept_id, c.angle, f"{c.score or 0:.3f}", flag)
            console.print(table)


@app.command("show")
def show_cmd(job_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=OrchestrationService(session).get(job_id).model_dump(mode="json"))


@app.command("approve")
def approve_cmd(
    job_id: str,
    gate: str | None = typer.Option(None, "--gate"),
    continue_pipeline: bool = typer.Option(True, "--continue/--stop"),
) -> None:
    _init()
    with get_session() as session:
        out = OrchestrationService(session).approve(
            ApproveJobRequest(
                job_id=job_id,
                gate=gate,  # type: ignore[arg-type]
                continue_pipeline=continue_pipeline,
            )
        )
        console.print_json(data=out.model_dump(mode="json"))


@app.command("retry")
def retry_cmd(job_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=OrchestrationService(session).retry(job_id).model_dump(mode="json"))


@app.command("list")
def list_cmd(status: str | None = typer.Option(None, "--status")) -> None:
    _init()
    with get_session() as session:
        rows = OrchestrationService(session).list_jobs(status=status)
        table = Table(title="Orchestration Jobs")
        table.add_column("ID")
        table.add_column("Status")
        table.add_column("Action")
        table.add_column("Priority")
        table.add_column("Character")
        for r in rows:
            table.add_row(
                r.job_id[:8],
                r.status,
                r.actionability or "",
                f"{r.priority:.3f}",
                r.character_slug or "",
            )
        console.print(table)


@app.command("lineage")
def lineage_cmd(job_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=OrchestrationService(session).lineage(job_id))


@app.command("decisions")
def decisions_cmd(job_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=OrchestrationService(session).decision_log(job_id))


@app.command("engines")
def engines_cmd(job_id: str) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=OrchestrationService(session).engine_runs(job_id))
