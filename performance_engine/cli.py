from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import PublicationReceipt, SocialAccount
from db.session import get_session, init_db, reset_engine
from performance_engine.schemas import (
    ContentFingerprint,
    RefreshRequest,
    StartTrackingRequest,
)
from performance_engine.service import PerformanceService
from publishing_engine.schemas import (
    ApprovalGate,
    CaptionSpec,
    ConnectAccountRequest,
    CreatePlanRequest,
    MediaRefs,
    PlatformTarget,
    PublishingPlanSpec,
    PublishingPolicy,
)
from publishing_engine.service import PublishingService
from config.settings import get_settings
from pathlib import Path
import json

app = typer.Typer(
    help="Performance & Analytics Engine — actual post metrics after publish",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


def _stub_media(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stub": True,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration_sec": 30,
        "video_codec": "h264",
        "audio_codec": "aac",
    }
    path.write_bytes(b"AMP_ASSEMBLY_STUB\n" + json.dumps(payload).encode())
    path.with_suffix(".meta.json").write_text(json.dumps(payload))


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    profile: str = typer.Option("viral", "--profile", help="normal|viral|slow"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Bootstrap a published receipt → collect multi-age performance curve."""
    _init()
    with get_session() as session:
        if not bootstrap:
            console.print("[red]Use --bootstrap for the V1 acceptance path[/red]")
            raise typer.Exit(1)

        settings = get_settings()
        media = Path(settings.storage_root) / "perf_bootstrap" / f"{uuid4().hex[:8]}.mp4"
        _stub_media(media)

        pub_svc = PublishingService(session)
        acct = pub_svc.connect_account(
            ConnectAccountRequest(
                platform="instagram",
                external_account_id=f"ig_perf_{uuid4().hex[:6]}",
                username="perf_bot",
                access_token="stub",
                stub_oauth=True,
            )
        )
        plan = pub_svc.create_plan(
            CreatePlanRequest(
                plan=PublishingPlanSpec(
                    content_id=f"content_perf_{uuid4().hex[:6]}",
                    approval=ApprovalGate(
                        qa_status="passed", approved=True, reviewer="bootstrap"
                    ),
                    platforms=[PlatformTarget(platform="instagram", account_id=acct.id)],
                    metadata=CaptionSpec(
                        title="You wouldn't open this door...",
                        body="Would you have opened it?",
                    ),
                    media=MediaRefs(
                        storage_uri=str(media),
                        duration_sec=30,
                        width=1080,
                        height=1920,
                    ),
                    policy=PublishingPolicy(
                        require_qa=True,
                        require_human_approval=True,
                        allowed_platforms=["instagram"],
                    ),
                    prediction_id="pred_perf_001",
                    character_slug="ghost_kid",
                    lineage={"prediction_id": "pred_perf_001", "character_slug": "ghost_kid"},
                    idempotency_key=f"perf:{uuid4().hex}",
                ),
                process=True,
            )
        )
        receipts = pub_svc.list_receipts(plan.id)
        if not receipts:
            console.print("[red]publish produced no receipt[/red]")
            raise typer.Exit(1)
        pub_id = receipts[0].id

        perf = PerformanceService(session)
        # Publishing already starts tracking; refresh across the first-hour schedule
        ages = [300, 900, 1800, 3600, 7200]
        for age in ages:
            perf.refresh(
                RefreshRequest(
                    publication_id=pub_id,
                    simulate_age_sec=age,
                    growth_profile=profile,  # type: ignore[arg-type]
                )
            )
        data = perf.get_performance(pub_id)
        if json_out:
            console.print_json(data=data)
        else:
            a = data["analytics"]
            console.print(
                Panel.fit(
                    f"[bold]Publication[/bold] {pub_id[:8]}\n"
                    f"views={a['views']} shares={a['shares']}\n"
                    f"engagement={a['engagement_rate']:.4f} virality={a['virality_score']:.3f}\n"
                    f"state={a['viral_state']} velocity={a['view_velocity_per_hour']:.0f}/h\n"
                    f"prediction_id={data['prediction_id']}",
                    title="performance run",
                )
            )


@app.command("show")
def show_cmd(publication_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=PerformanceService(session).get_performance(publication_id))


@app.command("timeseries")
def timeseries_cmd(
    publication_id: str = typer.Argument(...),
    metric: str = typer.Option("views", "--metric", "-m"),
) -> None:
    _init()
    with get_session() as session:
        rows = PerformanceService(session).get_timeseries(publication_id, metric=metric)
        table = Table(title=f"Timeseries: {metric}")
        table.add_column("timestamp")
        table.add_column("value")
        for r in rows:
            table.add_row(r["timestamp"], str(r["value"]))
        console.print(table)


@app.command("retention")
def retention_cmd(publication_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=PerformanceService(session).get_retention(publication_id))


@app.command("audience")
def audience_cmd(publication_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=PerformanceService(session).get_audience(publication_id) or {})


@app.command("benchmarks")
def benchmarks_cmd(
    publication_id: str = typer.Argument(...),
    metric: str = typer.Option("views", "--metric", "-m"),
) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=PerformanceService(session).get_benchmarks(publication_id, metric))


@app.command("refresh")
def refresh_cmd(
    publication_id: str = typer.Argument(...),
    age: int = typer.Option(3600, "--age", help="Simulated age since publish (sec)"),
    profile: str = typer.Option("normal", "--profile"),
) -> None:
    _init()
    with get_session() as session:
        snap = PerformanceService(session).refresh(
            RefreshRequest(
                publication_id=publication_id,
                simulate_age_sec=age,
                growth_profile=profile,  # type: ignore[arg-type]
            )
        )
        console.print(
            f"snapshot {snap.id[:8]} views={snap.metrics.get('views')} age={snap.age_since_publish_sec}s"
        )


@app.command("track")
def track_cmd(
    publication_id: str = typer.Argument(...),
    character: str = typer.Option("ghost_kid", "--character", "-c"),
) -> None:
    _init()
    with get_session() as session:
        job = PerformanceService(session).start_tracking(
            StartTrackingRequest(
                publication_id=publication_id,
                content_fingerprint=ContentFingerprint(character=character),
                collect_now=True,
                simulate_age_sec=300,
            )
        )
        console.print(f"tracking job {job.id[:8]} status={job.status}")


@app.command("list")
def list_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    _init()
    with get_session() as session:
        rows = list(
            session.scalars(
                select(PublicationReceipt).order_by(PublicationReceipt.created_at.desc()).limit(limit)
            ).all()
        )
        table = Table(title="Publications (receipts)")
        table.add_column("id")
        table.add_column("platform")
        table.add_column("content")
        table.add_column("post")
        for r in rows:
            table.add_row(
                r.id[:8],
                r.platform,
                (r.content_id or "")[:12],
                (r.external_post_id or "")[:16],
            )
        console.print(table)


if __name__ == "__main__":
    app()
