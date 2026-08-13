from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from assembly_engine.schemas import (
    AssemblySpecification,
    ClipSpec,
    CreateAssemblyRequest,
)
from assembly_engine.service import AssemblyService
from config.settings import get_settings
from db.models import PublishingPlan
from db.session import get_session, init_db, reset_engine
from publishing_engine.profiles import PLATFORM_PROFILES
from publishing_engine.registry import list_platforms
from publishing_engine.schemas import (
    ApprovalGate,
    CaptionSpec,
    ConnectAccountRequest,
    CreatePlanRequest,
    HashtagGroups,
    MediaRefs,
    PlatformTarget,
    PublishPlanRequest,
    PublishingPlanSpec,
    PublishingPolicy,
    SchedulePlanRequest,
    ScheduleSpec,
)
from publishing_engine.service import PublishingService
from sqlalchemy import select

app = typer.Typer(
    help="Publishing Engine — QA-gated multi-platform publish + receipts",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


def _stub_video(path: Path, duration: float = 30.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stub": True,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration_sec": duration,
        "video_codec": "h264",
        "audio_codec": "aac",
    }
    path.write_bytes(b"AMP_ASSEMBLY_STUB\n" + json.dumps(payload).encode("utf-8"))
    path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")


@app.command("connect")
def connect_cmd(
    platform: str = typer.Argument(..., help="instagram|youtube|tiktok"),
    external_id: str = typer.Option(..., "--external-id", "-e"),
    username: str = typer.Option(..., "--username", "-u"),
    token: str = typer.Option("stub_access_token", "--token"),
    timezone: str = typer.Option("Asia/Kolkata", "--timezone"),
    character: str | None = typer.Option(None, "--character", "-c"),
) -> None:
    """Connect a social account (stub OAuth stores encrypted credential reference)."""
    _init()
    with get_session() as session:
        acct = PublishingService(session).connect_account(
            ConnectAccountRequest(
                platform=platform,  # type: ignore[arg-type]
                external_account_id=external_id,
                username=username,
                display_name=username,
                timezone=timezone,
                character_slug=character,
                access_token=token,
                refresh_token="stub_refresh",
                scopes=["publishing", "analytics"],
                stub_oauth=True,
            )
        )
        console.print(f"connected {acct.platform} {acct.id[:8]} @{acct.username}")


@app.command("accounts")
def accounts_cmd(platform: str | None = typer.Option(None, "--platform", "-p")) -> None:
    _init()
    with get_session() as session:
        rows = PublishingService(session).list_accounts(platform=platform)
        table = Table(title="Social accounts")
        table.add_column("id")
        table.add_column("platform")
        table.add_column("username")
        table.add_column("status")
        table.add_column("token")
        for r in rows:
            table.add_row(r.id[:8], r.platform, r.username or "", r.status, r.token_status)
        console.print(table)


@app.command("disconnect")
def disconnect_cmd(account_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        acct = PublishingService(session).disconnect_account(account_id)
        console.print(f"disconnected {acct.id[:8]} ({acct.platform})")


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str = typer.Option("ghost_kid", "--character", "-c"),
    platforms: str = typer.Option("instagram,youtube", "--platforms"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Acceptance: connect accounts → assemble stub reel → QA pass → publish → verify."""
    _init()
    with get_session() as session:
        if not bootstrap:
            console.print("[red]Use --bootstrap for the V1 acceptance path[/red]")
            raise typer.Exit(1)

        svc = PublishingService(session)
        settings = get_settings()
        storage = Path(settings.storage_root)
        video_path = storage / "rendered" / "publish_bootstrap" / f"{uuid4().hex[:8]}.mp4"
        _stub_video(video_path, 30.0)

        # Minimal assembly so lineage exists
        assembly = AssemblyService(session).create(
            CreateAssemblyRequest(
                specification=AssemblySpecification(
                    content_id=f"content_{character}",
                    duration_sec=30,
                    video_clips=[
                        ClipSpec(
                            artifact_id=f"video_{uuid4().hex[:6]}",
                            storage_uri=str(video_path),
                            start=0,
                            end=30,
                            source_end=30,
                        )
                    ],
                ),
                process_render=True,
                render_quality="final",
            )
        )
        arts = AssemblyService(session).list_artifacts(assembly.id)
        master_id = arts[0].id if arts else None
        media_uri = arts[0].storage_uri if arts else str(video_path)

        accounts = {}
        for p in [x.strip() for x in platforms.split(",") if x.strip()]:
            accounts[p] = svc.connect_account(
                ConnectAccountRequest(
                    platform=p,  # type: ignore[arg-type]
                    external_account_id=f"{p}_{character}",
                    username=f"{character}_{p}",
                    display_name=f"{character} {p}",
                    timezone="Asia/Kolkata",
                    character_slug=character,
                    access_token=f"stub_token_{p}",
                    refresh_token=f"stub_refresh_{p}",
                    stub_oauth=True,
                )
            )

        plan = svc.create_plan(
            CreatePlanRequest(
                plan=PublishingPlanSpec(
                    content_id=assembly.content_id,
                    assembly_id=assembly.id,
                    approval=ApprovalGate(
                        qa_status="passed",
                        approved=True,
                        policy_risk="none",
                        reviewer="bootstrap",
                    ),
                    platforms=[
                        PlatformTarget(platform=p, account_id=a.id)  # type: ignore[arg-type]
                        for p, a in accounts.items()
                    ],
                    schedule=ScheduleSpec(mode="immediate"),
                    metadata=CaptionSpec(
                        title="You wouldn't open this door...",
                        body="Would you have opened it?",
                    ),
                    hashtags=HashtagGroups(
                        broad=["#story"],
                        niche=["#horrorstories"],
                        trend=["#shorts"],
                    ),
                    media=MediaRefs(
                        master_artifact_id=master_id,
                        storage_uri=media_uri,
                        duration_sec=30,
                        width=1080,
                        height=1920,
                        mime_type="video/mp4",
                    ),
                    policy=PublishingPolicy(
                        mode="approval_required",
                        require_qa=True,
                        require_human_approval=True,
                        allowed_platforms=list(accounts.keys()),  # type: ignore[arg-type]
                    ),
                    character_slug=character,
                    lineage={"assembly_id": assembly.id, "bootstrap": True},
                    idempotency_key=f"bootstrap:{assembly.id}",
                ),
                process=True,
            )
        )
        receipts = svc.list_receipts(plan.id)
        payload = {
            "plan_id": plan.id,
            "status": plan.status,
            "content_id": plan.content_id,
            "assembly_id": assembly.id,
            "receipts": [
                {
                    "id": r.id,
                    "platform": r.platform,
                    "external_post_id": r.external_post_id,
                    "url": r.post_url,
                    "verification_status": r.verification_status,
                }
                for r in receipts
            ],
        }
        if json_out:
            console.print_json(data=payload)
        else:
            lines = "\n".join(
                f"  {r['platform']}: {r['external_post_id']} ({r['verification_status']})"
                for r in payload["receipts"]
            )
            console.print(
                Panel.fit(
                    f"[bold]Plan[/bold] {plan.id[:8]} → {plan.status}\n"
                    f"content={plan.content_id}\n{lines}",
                    title="publish run",
                )
            )


@app.command("publish")
def publish_cmd(plan_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        plan = PublishingService(session).publish_plan(
            PublishPlanRequest(plan_id=plan_id, process=True)
        )
        console.print(f"plan {plan.id[:8]} → {plan.status}")


@app.command("approve")
def approve_cmd(
    plan_id: str = typer.Argument(...),
    reviewer: str = typer.Option("human", "--reviewer"),
) -> None:
    _init()
    with get_session() as session:
        plan = PublishingService(session).approve_plan(plan_id, reviewer=reviewer)
        console.print(f"approved {plan.id[:8]} by {reviewer}")


@app.command("schedule")
def schedule_cmd(
    plan_id: str = typer.Argument(...),
    hours: float = typer.Option(1.0, "--hours", help="Schedule N hours from now (UTC)"),
    timezone: str = typer.Option("Asia/Kolkata", "--timezone"),
) -> None:
    _init()
    when = datetime.now(timezone.utc) + timedelta(hours=hours)
    with get_session() as session:
        plan = PublishingService(session).schedule_plan(
            SchedulePlanRequest(plan_id=plan_id, publish_at=when, timezone=timezone)
        )
        console.print(f"scheduled {plan.id[:8]} at {when.isoformat()} ({timezone})")


@app.command("show")
def show_cmd(plan_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        svc = PublishingService(session)
        plan = svc.get_plan(plan_id)
        if not plan:
            console.print("[red]not found[/red]")
            raise typer.Exit(1)
        jobs = svc.list_jobs(plan.id)
        console.print_json(
            data={
                "id": plan.id,
                "content_id": plan.content_id,
                "status": plan.status,
                "approval": plan.approval,
                "jobs": [
                    {
                        "id": j.id,
                        "platform": j.platform,
                        "status": j.status,
                        "attempt": j.attempt,
                        "error": j.error,
                    }
                    for j in jobs
                ],
            }
        )


@app.command("receipt")
def receipt_cmd(job_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        out = PublishingService(session).get_receipt(job_id)
        if not out:
            console.print("[red]no receipt[/red]")
            raise typer.Exit(1)
        console.print_json(data=out.model_dump(mode="json"))


@app.command("retry")
def retry_cmd(job_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        job = PublishingService(session).retry_job(job_id)
        console.print(f"job {job.id[:8]} → {job.status}")


@app.command("list")
def list_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    _init()
    with get_session() as session:
        rows = list(
            session.scalars(
                select(PublishingPlan).order_by(PublishingPlan.created_at.desc()).limit(limit)
            ).all()
        )
        table = Table(title="Publishing plans")
        table.add_column("id")
        table.add_column("content")
        table.add_column("status")
        table.add_column("platforms")
        for r in rows:
            plats = ",".join(p.get("platform", "") for p in (r.platforms or []))
            table.add_row(r.id[:8], r.content_id[:16], r.status, plats)
        console.print(table)


@app.command("profiles")
def profiles_cmd() -> None:
    table = Table(title="Platform profiles")
    table.add_column("id")
    table.add_column("platform")
    table.add_column("type")
    table.add_column("max_dur")
    for pid, p in PLATFORM_PROFILES.items():
        table.add_row(pid, p["platform"], p["content_type"], str(p["max_duration_sec"]))
    console.print(table)


@app.command("providers")
def providers_cmd() -> None:
    console.print_json(data=list_platforms())


if __name__ == "__main__":
    app()
