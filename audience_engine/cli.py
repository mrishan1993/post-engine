from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from audience_engine.schemas import (
    AcceptOpportunityRequest,
    AnalyticsIn,
    CommentIn,
    IngestBatchRequest,
)
from audience_engine.service import AudienceService
from db.session import get_session, init_db, reset_engine

app = typer.Typer(
    help="Audience Intelligence & Community — signals, demands, opportunities",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


def _demo_comments(content_id: str) -> list[CommentIn]:
    samples = [
        ("Bring Character B back!!", "fan", 40),
        ("Where is Character B?", "follower", 12),
        ("WE WANT B", "fan", 55),
        ("Character A + Character B would be insane", "advocate", 90),
        ("Make A meet B please", "returning", 22),
        ("bhai ye character wapas lao 😂", "fan", 18),
        ("I love this so much", "follower", 5),
        ("How does this work?", "new", 1),
        ("Need longer episodes", "follower", 8),
        ("We need longer episodes honestly", "fan", 6),
        ("Please make longer episodes", "returning", 4),
        ("Longer episodes please!!", "fan", 7),
        ("I think Character A is going to quit", "follower", 3),
        ("This is the funniest thing I've seen", "advocate", 15),
        ("Can I be in the next episode?", "new", 2),
        ("Where can I buy this?", "follower", 1),
        ("Check my bio for free followers http://spam.example", "new", 0),
        ("Check my bio for free followers http://spam.example", "new", 0),  # duplicate
        ("first", "new", 0),
        ("Character A + Character B forever", "fan", 30),
        ("A and B together pls", "core", 11),
        ("Bring Character B back", "fan", 9),
        ("Where is Character B tho", "returning", 5),
        ("Character A meet Character B", "fan", 14),
        ("Pairing A + B is what we need", "advocate", 20),
    ]
    # normalize user_tier "core" -> fan
    out = []
    for text, tier, likes in samples:
        if tier == "core":
            tier = "fan"
        out.append(
            CommentIn(
                text=text,
                content_id=content_id,
                user_tier=tier,
                likes=likes,
                platform="instagram",
            )
        )
    return out


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    content_id: str = typer.Option("reel_demo_1", "--content-id"),
    accept: bool = typer.Option(False, "--accept"),
    strategy_id: str | None = typer.Option(None, "--strategy-id"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Ingest demo community signals → topics/demands/opportunities."""
    _init()
    with get_session() as session:
        if not bootstrap:
            console.print("[red]Use --bootstrap[/red]")
            raise typer.Exit(1)
        svc = AudienceService(session)
        overview = svc.ingest(
            IngestBatchRequest(
                comments=_demo_comments(content_id),
                analytics=[
                    AnalyticsIn(
                        content_id=content_id,
                        views=1_800_000,
                        likes=92_000,
                        shares=14_000,
                        comments=8_000,
                        completion_rate=0.72,
                        follows=12_000,
                        unfollows=400,
                        returning_viewer_rate=0.58,
                    )
                ],
                characters=["character_a", "character_b"],
                content_id=content_id,
                process=True,
            )
        )
        accepted = None
        if accept and overview.opportunities:
            top = overview.opportunities[0]
            accepted = svc.accept_opportunity(
                AcceptOpportunityRequest(
                    opportunity_id=top.opportunity_id,
                    strategy_id=strategy_id,
                    push_to_strategy=bool(strategy_id),
                    push_to_campaign=False,
                )
            )
        if json_out:
            console.print_json(
                data={
                    "overview": overview.model_dump(mode="json"),
                    "accepted": accepted.model_dump(mode="json") if accepted else None,
                }
            )
            return
        console.print(
            Panel(
                f"health={overview.community_health}\n"
                f"signals={overview.signal_count} noise={overview.noise_filtered}\n"
                f"topics={len(overview.topics)} demands={len(overview.demands)}\n"
                f"opportunities={len(overview.opportunities)} alerts={len(overview.alerts)}\n"
                f"accepted={accepted.opportunity_id if accepted else None}",
                title="Audience Intelligence",
            )
        )
        table = Table(title="Top Demands")
        table.add_column("Vol")
        table.add_column("Conf")
        table.add_column("Action")
        table.add_column("Subject")
        for d in overview.demands[:8]:
            table.add_row(
                str(d.volume),
                f"{d.confidence or 0:.2f}",
                d.recommended_action or "",
                d.subject[:50],
            )
        console.print(table)


@app.command("overview")
def overview_cmd(json_out: bool = typer.Option(False, "--json")) -> None:
    _init()
    with get_session() as session:
        out = AudienceService(session).overview()
        if json_out:
            console.print_json(data=out.model_dump(mode="json"))
        else:
            console.print(Panel(str(out.model_dump()), title="Overview"))


if __name__ == "__main__":
    app()
