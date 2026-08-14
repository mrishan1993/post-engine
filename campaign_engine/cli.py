from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from campaign_engine.schemas import (
    CreateCampaignRequest,
    ExecuteEpisodeRequest,
    InjectTrendRequest,
    OptimizeCampaignRequest,
    RecordPerformanceRequest,
)
from campaign_engine.service import CampaignService
from db.session import get_session, init_db, reset_engine

app = typer.Typer(
    help="Campaign & Content Portfolio — campaigns, series, episodes, franchises",
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
    episodes: int = typer.Option(5, "--episodes", "-n"),
    execute: bool = typer.Option(False, "--execute"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Bootstrap campaign → series → episodes (+ optional orchestrator handoff)."""
    _init()
    with get_session() as session:
        if not bootstrap:
            console.print("[red]Use --bootstrap[/red]")
            raise typer.Exit(1)
        svc = CampaignService(session)
        campaign = svc.create_campaign(
            CreateCampaignRequest(
                name="Meet Alex",
                campaign_type="character",
                character_slug=character,
                episode_count=episodes,
                series_name=f"{character.replace('_', ' ').title()} Tries Human Things",
                series_premise=f"{character} navigates everyday human situations",
                hypothesis=(
                    "A recurring character-led series will generate stronger follower "
                    "conversion than standalone trend content."
                ),
            )
        )
        series = campaign.series[0] if campaign.series else None
        injected = None
        if series and series.episodes:
            mid = series.episodes[min(3, len(series.episodes) - 1)]
            injected = svc.inject_trend(
                InjectTrendRequest(
                    campaign_id=campaign.campaign_id,
                    series_id=series.series_id,
                    episode_id=mid.episode_id,
                    trend_id="trend_unexpected_reveal",
                    viral_mechanism="unexpected_reveal",
                    title=f"{character} Tries the Trend",
                )
            )
        exec_out = None
        if execute and series and series.episodes:
            exec_out = svc.execute_episode(
                ExecuteEpisodeRequest(
                    episode_id=series.episodes[0].episode_id,
                    run_pipeline=False,
                    orchestration_mode="autonomous",
                    push_to_strategy=False,
                )
            )
        if json_out:
            console.print_json(
                data={
                    "campaign": campaign.model_dump(mode="json"),
                    "injected": injected.model_dump(mode="json") if injected else None,
                    "execution": exec_out,
                    "lineage": svc.lineage(
                        campaign.campaign_id,
                        episode_id=series.episodes[0].episode_id if series and series.episodes else None,
                    ),
                }
            )
            return
        console.print(
            Panel(
                f"campaign={campaign.campaign_id}\n"
                f"status={campaign.status}\n"
                f"series={len(campaign.series)}\n"
                f"episodes={sum(len(s.episodes) for s in campaign.series)}\n"
                f"injected={injected.episode_id if injected else None}\n"
                f"execution={exec_out}",
                title="Campaign Portfolio",
            )
        )
        if series:
            table = Table(title=series.name)
            table.add_column("#")
            table.add_column("Role")
            table.add_column("Audience")
            table.add_column("Title")
            table.add_column("Status")
            for ep in series.episodes:
                table.add_row(
                    str(ep.episode_number),
                    ep.narrative_role or "",
                    ep.audience_role or "",
                    (ep.title or "")[:40],
                    ep.status,
                )
            console.print(table)


@app.command("optimize")
def optimize_cmd(
    campaign_id: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Replan campaign from episode performance (extend / retire / franchise)."""
    _init()
    with get_session() as session:
        out = CampaignService(session).optimize(
            OptimizeCampaignRequest(campaign_id=campaign_id)
        )
        if json_out:
            console.print_json(data=out)
        else:
            console.print(Panel(str(out), title="Optimize"))


@app.command("performance")
def performance_cmd(
    episode_id: str = typer.Argument(...),
    views: float = typer.Option(..., "--views"),
    followers: float = typer.Option(0, "--followers"),
) -> None:
    """Record episode performance metrics."""
    _init()
    with get_session() as session:
        ep = CampaignService(session).record_performance(
            RecordPerformanceRequest(
                episode_id=episode_id,
                views=views,
                followers_gained=followers,
            )
        )
        console.print(f"{ep.episode_id} status={ep.status} perf={ep.performance}")


if __name__ == "__main__":
    app()
