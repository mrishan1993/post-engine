from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import get_settings
from db.session import get_session, init_db, reset_engine
from performance_engine.schemas import ContentFingerprint, StartTrackingRequest
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
from verification_engine.schemas import CreateVerificationRequest, PredictionSnapshot, PredictionTarget
from verification_engine.service import VerificationService

app = typer.Typer(
    help="Verification Engine — predicted vs actual → calibration + learning signals",
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
    viral: bool = typer.Option(True, "--viral/--not-viral"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Bootstrap publish → performance → verification (V1 acceptance path)."""
    _init()
    with get_session() as session:
        if not bootstrap:
            console.print("[red]Use --bootstrap for the V1 acceptance path[/red]")
            raise typer.Exit(1)

        settings = get_settings()
        media = Path(settings.storage_root) / "verify_bootstrap" / f"{uuid4().hex[:8]}.mp4"
        _stub_media(media)

        pub_svc = PublishingService(session)
        acct = pub_svc.connect_account(
            ConnectAccountRequest(
                platform="instagram",
                external_account_id=f"ig_{uuid4().hex[:8]}",
                username="verify_user",
                access_token="stub",
                stub_oauth=True,
            )
        )
        prediction = PredictionSnapshot(
            id=f"pred_{uuid4().hex[:8]}",
            content_id=f"content_{uuid4().hex[:8]}",
            model_id="virality_predictor",
            model_version="v4",
            predictions={
                "virality": {"probability": 0.78},
                "engagement": {"probability": 0.72},
                "completion": {"probability": 0.65},
                "share_rate": {"expected": 0.034},
                "views": {"expected": 1_000_000},
            },
            confidence={"overall": 0.81},
            target=PredictionTarget(metric="views", threshold=1_000_000, window_hours=48),
            signals={
                "trend_velocity": 0.91,
                "hook_strength": 0.88,
                "music_fit": 0.72,
            },
            segments={"platform": "instagram", "character": "ravi", "hook_type": "curiosity"},
        )
        plan = pub_svc.create_plan(
            CreatePlanRequest(
                plan=PublishingPlanSpec(
                    content_id=prediction.content_id or f"c_{uuid4().hex[:8]}",
                    approval=ApprovalGate(qa_status="passed", approved=True, reviewer="cli"),
                    platforms=[PlatformTarget(platform="instagram", account_id=acct.id)],
                    metadata=CaptionSpec(title="Hook", body="Would you open it?"),
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
                    prediction_id=prediction.id,
                    character_slug="ravi",
                    lineage={"prediction_id": prediction.id, "character_slug": "ravi"},
                    idempotency_key=f"verify_{uuid4().hex}",
                ),
                process=True,
            )
        )
        receipt = pub_svc.list_receipts(plan.id)[0]
        # Collect performance at ~48h with viral or slow profile
        PerformanceService(session).start_tracking(
            StartTrackingRequest(
                publication_id=receipt.id,
                content_fingerprint=ContentFingerprint(character="ravi", hook_type="curiosity"),
                prediction={
                    "model_id": prediction.model_id,
                    "model_version": prediction.model_version,
                    "virality": 0.78,
                    "engagement": 0.72,
                    "completion": 0.65,
                    "views": 1_000_000,
                    "share_rate": 0.034,
                    "confidence": 0.81,
                    "predictions": prediction.predictions,
                    "target": prediction.target.model_dump(),
                    "signals": prediction.signals,
                },
                collect_now=True,
                simulate_age_sec=48 * 3600,
                growth_profile="viral" if viral else "slow",
            )
        )
        result = VerificationService(session).create_run(
            CreateVerificationRequest(
                publication_id=receipt.id,
                prediction=prediction,
                stage="primary",
                process=True,
                qa_score=0.9,
            )
        )
        if json_out:
            console.print_json(data=result.model_dump(mode="json"))
            return

        table = Table(title="Predicted vs Actual")
        table.add_column("Metric")
        table.add_column("Predicted")
        table.add_column("Actual")
        table.add_column("Error / Outcome")
        for m in result.metrics:
            err = (
                f"outcome={m.outcome}"
                if m.outcome is not None and m.metric == "viral_target"
                else (f"rel={m.relative_error}" if m.relative_error is not None else "—")
            )
            table.add_row(
                m.metric,
                str(m.predicted_value),
                str(m.actual_value),
                err,
            )
        console.print(table)
        console.print(
            Panel(
                f"status={result.status}  label={result.confidence_label}\n"
                f"brier={result.brier_score}  log_loss={result.log_loss}\n"
                f"signals={len(result.learning_signals)}  verification={result.verification_id}",
                title="Verification",
            )
        )


@app.command("show")
def show_cmd(verification_id: str) -> None:
    _init()
    with get_session() as session:
        result = VerificationService(session).get(verification_id)
        console.print_json(data=result.model_dump(mode="json"))


@app.command("prediction")
def prediction_cmd(prediction_ref: str) -> None:
    _init()
    with get_session() as session:
        rows = VerificationService(session).get_by_prediction(prediction_ref)
        console.print_json(data=[r.model_dump(mode="json") for r in rows])


@app.command("calibration")
def calibration_cmd(
    model_id: str = typer.Argument("virality_predictor"),
    version: str | None = typer.Option(None, "--version"),
    metric: str = typer.Option("viral_target", "--metric"),
) -> None:
    _init()
    with get_session() as session:
        rows = VerificationService(session).calibration(
            model_id, model_version=version, metric=metric
        )
        table = Table(title=f"Calibration — {model_id}")
        table.add_column("Bucket")
        table.add_column("n")
        table.add_column("mean_p")
        table.add_column("actual")
        table.add_column("error")
        table.add_column("segment")
        for r in rows:
            table.add_row(
                r["probability_bucket"],
                str(r["sample_count"]),
                f"{r['mean_prediction']:.3f}",
                f"{r['actual_success_rate']:.3f}",
                f"{r['calibration_error']:+.3f}",
                r["segment_key"],
            )
        console.print(table)


@app.command("performance")
def performance_cmd(
    model_id: str = typer.Argument("virality_predictor"),
    version: str | None = typer.Option(None, "--version"),
) -> None:
    _init()
    with get_session() as session:
        data = VerificationService(session).model_performance(model_id, model_version=version)
        console.print_json(data=data)


@app.command("signals")
def signals_cmd(
    prediction_ref: str | None = typer.Option(None, "--prediction"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    _init()
    with get_session() as session:
        rows = VerificationService(session).learning_signals(
            prediction_ref=prediction_ref, limit=limit
        )
        console.print_json(data=rows)


@app.command("compare")
def compare_cmd(
    model_a: str = typer.Argument(..., help="id or id:version"),
    model_b: str = typer.Argument(..., help="id or id:version"),
) -> None:
    _init()
    with get_session() as session:
        data = VerificationService(session).compare_models(
            {"model_a": model_a, "model_b": model_b}
        )
        console.print_json(data=data)
