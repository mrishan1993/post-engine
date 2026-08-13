from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from assembly_engine.schemas import (
    AssemblySpecification,
    AudioClipSpec,
    CaptionClipSpec,
    ClipSpec,
    CreateAssemblyRequest,
    DuckingSpec,
    OverlaySpec,
    SceneBlock,
)
from assembly_engine.service import AssemblyService
from config.settings import get_settings
from db.models import QaRun
from db.session import get_session, init_db, reset_engine
from qa_engine.schemas import CreateQaRunRequest, QaIssueSpec
from qa_engine.service import QAService

app = typer.Typer(
    help="QA Engine — multi-dimension gate before publishing",
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


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    assembly_id: str | None = typer.Option(None, "--assembly", "-a"),
    character: str = typer.Option("ghost_kid", "--character", "-c"),
    inject: str | None = typer.Option(
        None, "--inject", help="Inject issue code e.g. CHARACTER_DRIFT or POLICY_HIGH"
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run QA on an assembly (or bootstrap a stub reel)."""
    _init()
    with get_session() as session:
        if bootstrap and not assembly_id:
            settings = get_settings()
            path = Path(settings.storage_root) / "rendered" / "qa_bootstrap" / f"{uuid4().hex[:8]}.mp4"
            _stub_video(path, 30)
            assembly = AssemblyService(session).create(
                CreateAssemblyRequest(
                    specification=AssemblySpecification(
                        content_id=f"content_qa_{character}",
                        duration_sec=30,
                        scenes=[
                            SceneBlock(scene_id="scene_001", start=0, end=10),
                            SceneBlock(scene_id="scene_002", start=10, end=20),
                            SceneBlock(scene_id="scene_003", start=20, end=30),
                        ],
                        video_clips=[
                            ClipSpec(
                                artifact_id="v1",
                                storage_uri=str(path),
                                start=0,
                                end=30,
                                source_end=30,
                            )
                        ],
                        voice_clips=[
                            AudioClipSpec(
                                artifact_id="voice_1",
                                storage_uri=str(path),
                                start=0.2,
                                end=2.6,
                                metadata={"text": "Don't open that door."},
                            )
                        ],
                        music_clips=[
                            AudioClipSpec(
                                artifact_id="music_1",
                                storage_uri=str(path),
                                start=0,
                                end=30,
                                volume_db=-12,
                            )
                        ],
                        captions=[
                            CaptionClipSpec(
                                text="DON'T OPEN THAT DOOR.",
                                start=0.2,
                                end=1.8,
                                position="bottom_safe",
                            )
                        ],
                        overlays=[
                            OverlaySpec(
                                text="Follow for Part 2",
                                start=26.5,
                                end=30,
                                role="cta",
                            )
                        ],
                        ducking=DuckingSpec(target_db=-20, bed_db=-12),
                        captions_enabled=True,
                    ),
                    process_render=True,
                )
            )
            assembly_id = assembly.id
            console.print(f"[dim]Bootstrapped assembly[/dim] {assembly_id[:8]}")

        if not assembly_id:
            console.print("[red]Provide --assembly or --bootstrap[/red]")
            raise typer.Exit(1)

        injected = []
        force_risk = None
        if inject == "CHARACTER_DRIFT":
            injected.append(
                QaIssueSpec(
                    code="CHARACTER_DRIFT",
                    severity="high",
                    category="character",
                    scene_id="scene_003",
                    score=0.58,
                    message="Injected character drift",
                    recommended_action="regenerate",
                )
            )
        elif inject == "POLICY_HIGH":
            force_risk = "high"
        elif inject == "MUSIC_TOO_LOUD":
            injected.append(
                QaIssueSpec(
                    code="MUSIC_TOO_LOUD",
                    severity="medium",
                    category="audio",
                    message="Injected loud music",
                    recommended_action="repair",
                )
            )

        run = QAService(session).create(
            CreateQaRunRequest(
                assembly_id=assembly_id,
                character_slug=character,
                process=True,
                prediction={"virality_probability": 0.72, "engagement_probability": 0.81},
                force_safety_risk=force_risk,  # type: ignore[arg-type]
                injected_issues=injected,
            )
        )
        payload = {
            "qa_run_id": run.id,
            "decision": run.decision,
            "overall_score": float(run.overall_score or 0),
            "dimensions": run.dimension_scores,
            "status": run.status,
            "publishing_approval": QAService(session).to_publishing_approval(run.id),
        }
        if json_out:
            console.print_json(data=payload)
        else:
            console.print(
                Panel.fit(
                    f"[bold]QA[/bold] {run.id[:8]}\n"
                    f"decision={run.decision} score={payload['overall_score']:.3f}\n"
                    f"status={run.status}",
                    title="qa run",
                )
            )


@app.command("show")
def show_cmd(qa_run_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        run = QAService(session).get(qa_run_id)
        if not run:
            console.print("[red]not found[/red]")
            raise typer.Exit(1)
        console.print_json(
            data={
                "id": run.id,
                "content_id": run.content_id,
                "decision": run.decision,
                "overall_score": float(run.overall_score or 0),
                "dimensions": run.dimension_scores,
                "status": run.status,
                "result": run.result,
            }
        )


@app.command("issues")
def issues_cmd(qa_run_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        rows = QAService(session).list_issues(qa_run_id)
        table = Table(title="QA issues")
        table.add_column("code")
        table.add_column("sev")
        table.add_column("owner")
        table.add_column("action")
        table.add_column("scene")
        table.add_column("message")
        for r in rows:
            table.add_row(
                r.issue_code,
                r.severity,
                r.owner_engine or "",
                r.recommended_action or "",
                r.scene_id or "",
                (r.description or "")[:48],
            )
        console.print(table)


@app.command("approve")
def approve_cmd(
    qa_run_id: str = typer.Argument(...),
    reviewer: str = typer.Option("human", "--reviewer"),
) -> None:
    _init()
    with get_session() as session:
        run = QAService(session).approve(qa_run_id, reviewer=reviewer)
        console.print(f"approved {run.id[:8]} → {run.decision}")


@app.command("reject")
def reject_cmd(
    qa_run_id: str = typer.Argument(...),
    reviewer: str = typer.Option("human", "--reviewer"),
    reason: str = typer.Option("rejected", "--reason"),
) -> None:
    _init()
    with get_session() as session:
        run = QAService(session).reject(qa_run_id, reviewer=reviewer, reasons=[reason])
        console.print(f"rejected {run.id[:8]} → {run.decision}")


@app.command("repair")
def repair_cmd(qa_run_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        out = QAService(session).request_repair(qa_run_id)
        console.print_json(data=out)


@app.command("regenerate")
def regenerate_cmd(qa_run_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        out = QAService(session).request_regenerate(qa_run_id)
        console.print_json(data=out)


@app.command("approval")
def approval_cmd(qa_run_id: str = typer.Argument(...)) -> None:
    """Show Publishing ApprovalGate mapping for this QA run."""
    _init()
    with get_session() as session:
        console.print_json(data=QAService(session).to_publishing_approval(qa_run_id))


@app.command("list")
def list_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    _init()
    with get_session() as session:
        rows = list(
            session.scalars(select(QaRun).order_by(QaRun.created_at.desc()).limit(limit)).all()
        )
        table = Table(title="QA runs")
        table.add_column("id")
        table.add_column("content")
        table.add_column("decision")
        table.add_column("score")
        table.add_column("status")
        for r in rows:
            table.add_row(
                r.id[:8],
                r.content_id[:14],
                r.decision or "",
                str(r.overall_score or ""),
                r.status,
            )
        console.print(table)


if __name__ == "__main__":
    app()
