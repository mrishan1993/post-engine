from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from db.models import VoiceGenerationRequest, VoiceTimelineRow
from db.session import get_session, init_db, reset_engine
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService
from voice_generation_engine.capabilities import list_voice_providers
from voice_generation_engine.schemas import (
    DialogueLine,
    DialogueScript,
    ProviderStrategy,
    VoiceGenerationRequestIn,
    VoiceSpecification,
)
from voice_generation_engine.service import VoiceGenerationService
from voice_generation_engine.spec_builder import build_voice_spec_from_text

app = typer.Typer(
    help="Voice Generation Engine — VoiceSpecification → voice artifacts + timeline",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("run")
def run_cmd(
    storyboard_id: str | None = typer.Option(None, "--storyboard", "-b"),
    character: str | None = typer.Option(None, "--character", "-c"),
    text: str | None = typer.Option(None, "--text", "-t"),
    emotion: str = typer.Option("fear", "--emotion"),
    variants: int = typer.Option(2, "--variants", "-n"),
    provider: str = typer.Option("provider_a", "--provider"),
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Acceptance: character + dialogue → takes + timestamps + timeline."""
    _init()
    with get_session() as session:
        if bootstrap and not storyboard_id and not text:
            stories = StoryService(session).generate(
                StoryRequest.model_validate(
                    {
                        "content_opportunity": {
                            "topic": "POV horror",
                            "emotion": "fear",
                            "platform": "instagram_reels",
                        },
                        "creative_direction": {
                            "format": "POV",
                            "target_duration_sec": 30,
                            "visual_style": "cinematic_horror",
                        },
                        "characters": (
                            [{"character_slug": character, "role": "protagonist"}]
                            if character
                            else [{"character_slug": "ghost_kid", "role": "protagonist"}]
                        ),
                        "candidate_count": 1,
                        "story_type": "pov_horror",
                    }
                )
            )
            board = StoryboardService(session).generate(
                StoryboardRequest(
                    story_id=stories[0].id,
                    character_slugs=[character or "ghost_kid"],
                    location_query="Haunted School",
                )
            )
            storyboard_id = board.id
            console.print(f"[dim]Bootstrapped storyboard[/dim] {storyboard_id[:8]}")

        payload: VoiceGenerationRequestIn
        if text:
            spec = build_voice_spec_from_text(
                text=text,
                character_slug=character,
                emotion=emotion,
                intensity=0.75,
            )
            payload = VoiceGenerationRequestIn(
                character_slug=character,
                voice_spec=spec,
                variants={"count": variants, "strategy": "different_emotion"},
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred=provider, fallback=["provider_b"]
                ),
                process=True,
                build_timeline=True,
            )
        elif storyboard_id:
            payload = VoiceGenerationRequestIn(
                storyboard_id=storyboard_id,
                character_slug=character,
                variants={"count": variants, "strategy": "different_emotion"},
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred=provider, fallback=["provider_b"]
                ),
                process=True,
                build_timeline=True,
            )
        else:
            # Demo multi-character dialogue
            payload = VoiceGenerationRequestIn(
                character_slug=character or "ghost_kid",
                dialogue=DialogueScript(
                    lines=[
                        DialogueLine(
                            speaker=character or "ghost_kid",
                            line="Wait... did you hear that?",
                            emotion="fear",
                            intensity=0.75,
                        ),
                        DialogueLine(
                            speaker=character or "ghost_kid",
                            line="Don't open that door.",
                            emotion="fear",
                            intensity=0.85,
                        ),
                    ]
                ),
                variants={"count": variants, "strategy": "different_emotion"},
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred=provider, fallback=["provider_b"]
                ),
                process=True,
                build_timeline=True,
            )

        req = VoiceGenerationService(session).create(payload)
        arts = VoiceGenerationService(session).list_artifacts(req.id)
        tl = session.scalar(
            select(VoiceTimelineRow).order_by(VoiceTimelineRow.created_at.desc())
        )
        if json_out:
            best = max(
                arts,
                key=lambda a: float((a.technical_qa or {}).get("technical_score") or 0),
                default=None,
            )
            console.print_json(
                json.dumps(
                    {
                        "request_id": req.id,
                        "status": req.status,
                        "artifact_id": best.id if best else None,
                        "character_id": req.character_id,
                        "voice_profile_id": req.voice_profile_id,
                        "duration_sec": float(best.duration_sec or 0) if best else None,
                        "provider": best.provider if best else None,
                        "timestamps_available": bool(
                            best and best.timestamps and best.timestamps.get("words")
                        ),
                        "variants": [
                            {
                                "artifact_id": a.id,
                                "quality_score": (a.technical_qa or {}).get("technical_score"),
                                "duration_sec": float(a.duration_sec or 0),
                            }
                            for a in arts
                        ],
                        "timeline_id": tl.id if tl else None,
                    },
                    default=str,
                )
            )
            return

        console.print(
            Panel.fit(
                f"status={req.status} takes={len(arts)} "
                f"voice={req.voice_profile_id[:8] if req.voice_profile_id else '-'}",
                title=req.id,
            )
        )
        for a in arts:
            words = len((a.timestamps or {}).get("words") or [])
            console.print(
                f"  [green]{a.id[:8]}[/green] {float(a.duration_sec or 0):.2f}s "
                f"words={words} qa={(a.technical_qa or {}).get('technical_score')}"
            )


@app.command("profiles")
def profiles_cmd() -> None:
    _init()
    with get_session() as session:
        table = Table(title="Voice Profiles")
        table.add_column("Slug")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Providers")
        for p in VoiceGenerationService(session).list_profiles():
            maps = p.provider_mappings or {}
            table.add_row(
                p.slug,
                p.name,
                p.status,
                ",".join(k for k, v in maps.items() if v)[:40],
            )
        console.print(table)


@app.command("character")
def character_cmd(character: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        info = VoiceGenerationService(session).get_character_voice(character)
        console.print_json(json.dumps(info, default=str))


@app.command("timeline")
def timeline_cmd(timeline_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        tl = VoiceGenerationService(session).get_timeline(timeline_id)
        if not tl:
            console.print("[red]Not found[/red]")
            raise typer.Exit(1)
        console.print_json(
            json.dumps(
                {
                    "timeline_id": tl.id,
                    "duration_sec": float(tl.duration_sec),
                    "segments": tl.segments,
                },
                default=str,
            )
        )


@app.command("show")
def show_cmd(request_id: str = typer.Argument(...)) -> None:
    _init()
    with get_session() as session:
        req = session.get(VoiceGenerationRequest, request_id)
        if not req:
            rows = list(
                session.scalars(
                    select(VoiceGenerationRequest).where(
                        VoiceGenerationRequest.id.startswith(request_id)
                    )
                ).all()
            )
            if len(rows) != 1:
                console.print("[red]Not found[/red]")
                raise typer.Exit(1)
            req = rows[0]
        jobs = VoiceGenerationService(session).list_jobs(req.id)
        table = Table(title=f"Voice Jobs — {req.id[:8]}")
        table.add_column("Job")
        table.add_column("Var")
        table.add_column("Provider")
        table.add_column("Voice")
        table.add_column("Status")
        for j in jobs:
            table.add_row(
                j.id[:8],
                str(j.variant_number),
                j.provider or "",
                (j.provider_voice_id or "")[:16],
                j.status,
            )
        console.print(table)


@app.command("providers")
def providers_cmd() -> None:
    table = Table(title="Voice Providers")
    table.add_column("ID")
    table.add_column("Model")
    table.add_column("Emotion")
    table.add_column("Timestamps")
    for p in list_voice_providers():
        caps = p.get("capabilities") or {}
        table.add_row(
            p["id"],
            str(p.get("model") or ""),
            str(caps.get("emotion_control")),
            str(caps.get("word_timestamps")),
        )
    console.print(table)


if __name__ == "__main__":
    app()
