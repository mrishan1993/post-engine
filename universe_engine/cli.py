from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from db.session import get_session, init_db, reset_engine
from universe_engine.schemas import (
    AssembleContextRequest,
    CreateCharacterRequest,
    CreateUniverseRequest,
    RecordEventRequest,
    UpsertRelationshipRequest,
    ValidateContinuityRequest,
)
from universe_engine.service import UniverseService

app = typer.Typer(
    help="Character & Content Universe Intelligence — canon, memory, continuity",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Bootstrap universe → characters → events → context → continuity check."""
    _init()
    with get_session() as session:
        if not bootstrap:
            console.print("[red]Use --bootstrap[/red]")
            raise typer.Exit(1)
        svc = UniverseService(session)
        universe = svc.create_universe(
            CreateUniverseRequest(
                name="Hotel Stories",
                slug="hotel_stories",
                description="Contemporary hotel comedy-drama universe",
                rules={"setting": "hotel", "tone": "comedic_drama"},
            )
        )
        alex = svc.create_character(
            CreateCharacterRequest(
                universe_id=universe.universe_id,
                slug="alex",
                name="Alex",
                identity={"occupation": "hotel_employee", "location": "Delhi"},
                personality={"traits": ["introverted", "funny", "anxious", "curious"]},
                personality_scores={
                    "confidence": 0.3,
                    "humor": 0.82,
                    "curiosity": 0.74,
                    "patience": 0.28,
                },
                goals=["Become a manager"],
                fears=["Public embarrassment"],
                behavioral_rules=[
                    "Avoids confrontation.",
                    "Uses humor under stress.",
                    "Overthinks decisions.",
                    "Never lies about family.",
                ],
                voice={
                    "sentence_length": "short",
                    "humor": "sarcastic",
                    "language_preferences": ["en", "hinglish"],
                },
            )
        )
        bee = svc.create_character(
            CreateCharacterRequest(
                universe_id=universe.universe_id,
                slug="character_b",
                name="Character B",
                identity={"occupation": "guest"},
                personality={"traits": ["confident", "sarcastic"]},
                personality_scores={"confidence": 0.8, "humor": 0.7},
            )
        )
        svc.record_event(
            RecordEventRequest(
                universe_id=universe.universe_id,
                description="Alex accidentally embarrasses himself in front of a guest.",
                action="public_embarrassment",
                participants=[alex.character_id],
                episode_key="ep1",
                emotional_impact=0.85,
                consequences=["Anxiety increased"],
                canon_status="canon",
            )
        )
        svc.upsert_relationship(
            UpsertRelationshipRequest(
                universe_id=universe.universe_id,
                source_id=alex.character_id,
                target_id=bee.character_id,
                relationship_type="acquaintance",
                strength=0.4,
            )
        )
        svc.record_event(
            RecordEventRequest(
                universe_id=universe.universe_id,
                description="Alex meets Character B at the hotel lobby.",
                participants=[alex.character_id, bee.character_id],
                episode_key="ep10",
                emotional_impact=0.5,
                canon_status="canon",
            )
        )
        svc.upsert_relationship(
            UpsertRelationshipRequest(
                universe_id=universe.universe_id,
                source_id=alex.character_id,
                target_id=bee.character_id,
                relationship_type="friend",
                strength=0.7,
                traits={"trust": 0.6},
            )
        )
        ctx = svc.assemble_context(
            AssembleContextRequest(
                universe_id=universe.universe_id,
                character_slugs=["alex", "character_b"],
                premise="Alex and B go on a hotel adventure",
            )
        )
        report = svc.validate_continuity(
            ValidateContinuityRequest(
                universe_id=universe.universe_id,
                premise="Alex meets Character B for the first time.",
                character_slugs=["alex", "character_b"],
                behavioral_actions=["Alex immediately starts a physical confrontation."],
            )
        )
        snap = svc.snapshot({"universe_id": universe.universe_id, "label": "after_ep10"})
        if json_out:
            console.print_json(
                data={
                    "universe": universe.model_dump(mode="json"),
                    "context": ctx.model_dump(mode="json"),
                    "continuity": report.model_dump(mode="json"),
                    "snapshot": snap,
                }
            )
            return
        console.print(
            Panel(
                f"universe={universe.universe_id}\n"
                f"alex={alex.character_id}\n"
                f"memories={len(ctx.memories)} rels={len(ctx.relationship_context)}\n"
                f"continuity={report.result}\n"
                f"snapshot={snap['snapshot_id']}",
                title="Universe Intelligence",
            )
        )
        table = Table(title="Warnings / Failures")
        table.add_column("Sev")
        table.add_column("Issue")
        for w in report.warnings + report.failures:
            table.add_row(w.get("severity", ""), (w.get("description") or "")[:80])
        console.print(table)


if __name__ == "__main__":
    app()
