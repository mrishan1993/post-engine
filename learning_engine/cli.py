from __future__ import annotations

from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from db.session import get_session, init_db, reset_engine
from learning_engine.schemas import (
    CreateExperimentRequest,
    RecommendRequest,
    ScopeSpec,
    TrainModelRequest,
)
from learning_engine.service import LearningService

app = typer.Typer(
    help="Learning & Optimization — patterns, profiles, briefs, experiments",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


def _seed_demo_observations(svc: LearningService, n: int = 40) -> None:
    """Deterministic-ish demo dataset for bootstrap / acceptance."""
    hooks = ["curiosity", "curiosity", "curiosity", "question", "shock", "generic"]
    stories = ["mystery", "mystery", "suspense", "comedy"]
    durations = [24, 26, 27, 18, 32, 22]
    for i in range(n):
        hook = hooks[i % len(hooks)]
        story = stories[i % len(stories)]
        dur = durations[i % len(durations)]
        # Curiosity + mystery + 22-28s perform better in the synthetic world
        base_completion = 0.55
        if hook == "curiosity":
            base_completion += 0.12
        if hook == "generic":
            base_completion -= 0.08
        if story == "mystery":
            base_completion += 0.08
        if story == "comedy":
            base_completion -= 0.06
        if 22 <= dur <= 28:
            base_completion += 0.05
        share = 0.02 + (0.015 if hook == "curiosity" else 0.0)
        views = 80_000 + i * 3_000 + (40_000 if hook == "curiosity" else 0)
        hour = 19 if i % 3 == 0 else (12 if i % 3 == 1 else 9)
        svc.add_observation(
            {
                "feature_vector": {
                    "character": "ravi",
                    "platform": "instagram",
                    "hook_type": hook,
                    "story_type": story,
                    "trend_category": "mystery_trend" if story == "mystery" else "general",
                    "duration_sec": dur,
                    "duration_bucket": "25-30"
                    if dur >= 25
                    else "20-25"
                    if dur >= 20
                    else "15-20"
                    if dur >= 15
                    else "30-45",
                    "hour": hour,
                    "predicted_virality": 0.72 if story == "mystery" else 0.55,
                    "verification_stage": "primary",
                },
                "outcome_vector": {
                    "views": views,
                    "completion_rate": round(min(0.95, base_completion + (i % 5) * 0.01), 4),
                    "share_rate": round(share + (i % 4) * 0.002, 4),
                    "engagement_rate": round(0.04 + (0.02 if hook == "curiosity" else 0), 4),
                    "virality_score": round(0.5 + (0.2 if hook == "curiosity" else 0), 4),
                    "followers_gained": 20 + i,
                },
                "confidence": 0.85,
            }
        )


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    character: str = typer.Option("ravi", "--character", "-c"),
    platform: str = typer.Option("instagram", "--platform", "-p"),
    seed_n: int = typer.Option(40, "--seed-n"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Bootstrap observations → patterns → Content Optimization Brief."""
    _init()
    with get_session() as session:
        svc = LearningService(session)
        if bootstrap:
            _seed_demo_observations(svc, n=seed_n)
        out = svc.brief(character=character, platform=platform, persist=True)
        if json_out:
            console.print_json(data=out)
            return
        brief = out.get("brief") or {}
        recs = brief.get("recommendations") or {}
        console.print(
            Panel(
                f"character={character} platform={platform}\n"
                f"observations={out['observation_count']} confidence={out['confidence']}\n"
                f"hook={recs.get('hook')}\n"
                f"story={recs.get('story')}\n"
                f"duration={recs.get('duration')}\n"
                f"exploration={brief.get('exploration')}\n"
                f"profile={out['profile_id']}",
                title="Content Optimization Brief",
            )
        )
        table = Table(title="Top recommendations")
        table.add_column("Target")
        table.add_column("Action")
        table.add_column("Confidence")
        table.add_column("n")
        for r in out.get("recommendations") or []:
            table.add_row(
                r.get("target", ""),
                r.get("action", ""),
                f"{r.get('confidence', 0):.2f}",
                str((r.get("evidence") or {}).get("sample_size", "")),
            )
        console.print(table)


@app.command("profile")
def profile_cmd(
    character: str | None = typer.Option(None, "--character", "-c"),
    platform: str | None = typer.Option(None, "--platform", "-p"),
) -> None:
    _init()
    with get_session() as session:
        p = LearningService(session).get_profile(character=character, platform=platform)
        if not p:
            console.print("[yellow]No active profile — run `learn run --bootstrap`[/yellow]")
            raise typer.Exit(1)
        console.print_json(data=p.model_dump(mode="json"))


@app.command("recommend")
def recommend_cmd(
    character: str = typer.Option("ravi", "--character", "-c"),
    platform: str = typer.Option("instagram", "--platform", "-p"),
) -> None:
    _init()
    with get_session() as session:
        out = LearningService(session).recommend(
            RecommendRequest(scope=ScopeSpec(character=character, platform=platform))
        )
        console.print_json(data=out.model_dump(mode="json"))


@app.command("patterns")
def patterns_cmd(
    character: str | None = typer.Option(None, "--character", "-c"),
    platform: str | None = typer.Option(None, "--platform", "-p"),
) -> None:
    _init()
    with get_session() as session:
        rows = LearningService(session).patterns(character=character, platform=platform)
        table = Table(title="Patterns (association)")
        table.add_column("Dim")
        table.add_column("Value")
        table.add_column("n")
        table.add_column("lift")
        table.add_column("status")
        for r in sorted(rows, key=lambda x: -x["lift"])[:30]:
            table.add_row(
                r["dimension"],
                r["value"],
                str(r["sample_size"]),
                f"{r['lift']:+.3f}",
                r["evidence_status"],
            )
        console.print(table)


@app.command("learning")
def learning_cmd(
    character: str | None = typer.Option(None, "--character", "-c"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    _init()
    with get_session() as session:
        rows = LearningService(session).list_learning(character=character, limit=limit)
        console.print_json(data=rows)


@app.command("character")
def character_cmd(character_id: str = typer.Argument("ravi")) -> None:
    _init()
    with get_session() as session:
        console.print_json(data=LearningService(session).character(character_id))


@app.command("trends")
def trends_cmd() -> None:
    _init()
    with get_session() as session:
        console.print_json(data=LearningService(session).trends())


@app.command("experiment")
def experiment_cmd(
    create: bool = typer.Option(False, "--create"),
    hypothesis: str = typer.Option("Curiosity hooks improve completion", "--hypothesis"),
    variable: str = typer.Option("hook_type", "--variable"),
    assign: str | None = typer.Option(None, "--assign", help="experiment id"),
    show: str | None = typer.Option(None, "--show"),
) -> None:
    _init()
    with get_session() as session:
        svc = LearningService(session)
        if create:
            exp = svc.create_experiment(
                CreateExperimentRequest(
                    hypothesis=hypothesis,
                    variable=variable,
                    control={"hook_type": "curiosity"},
                    variants=[{"hook_type": "question"}],
                    target_metric="completion_rate",
                    sample_target=30,
                    scope=ScopeSpec(character="ravi", platform="instagram"),
                )
            )
            console.print_json(data=exp)
            return
        if assign:
            console.print_json(data=svc.assign_experiment(assign))
            return
        if show:
            console.print_json(data=svc.get_experiment(show))
            return
        console.print_json(data=svc.list_experiments())


@app.command("train")
def train_cmd(
    model: str = typer.Option("virality_predictor", "--model"),
    version: str | None = typer.Option(None, "--version"),
) -> None:
    _init()
    with get_session() as session:
        out = LearningService(session).train_model(
            TrainModelRequest(model_name=model, version=version or f"v_{uuid4().hex[:6]}")
        )
        console.print_json(data=out)


@app.command("models")
def models_cmd(
    promote: str | None = typer.Option(None, "--promote", help="model id"),
    compare: str | None = typer.Option(None, "--compare", help="id_a,id_b"),
) -> None:
    _init()
    with get_session() as session:
        svc = LearningService(session)
        if promote:
            console.print_json(
                data=svc.promote_model({"model_id": promote, "require_better_than_champion": False})
            )
            return
        if compare:
            a, b = compare.split(",", 1)
            console.print_json(data=svc.compare_models(a.strip(), b.strip()))
            return
        console.print_json(data=svc.list_models())


@app.command("ingest")
def ingest_cmd(verification_id: str) -> None:
    _init()
    with get_session() as session:
        out = LearningService(session).ingest_verification(verification_id)
        console.print_json(data=out or {"error": "not found"})
