from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import NarrativePattern
from story_engine.schemas import StoryBlueprint


DEFAULT_PATTERNS: list[dict[str, Any]] = [
    {
        "name": "Mystery Voice",
        "pattern_type": "pov_horror",
        "structure": {
            "hook": "warning",
            "setup": "discovery",
            "conflict": "unknown_source",
            "escalation": "source_gets_closer",
            "twist": "source_is_personal_device",
            "ending": "loop_or_question",
        },
    },
    {
        "name": "Curiosity Challenge",
        "pattern_type": "kids_challenge",
        "structure": {
            "hook": "challenge",
            "setup": "game",
            "conflict": "puzzle",
            "escalation": "harder_beats",
            "ending": "emotional_payoff",
            "omit_twist": True,
        },
    },
]


def ensure_default_patterns(session: Session) -> int:
    created = 0
    for p in DEFAULT_PATTERNS:
        exists = session.scalar(select(NarrativePattern).where(NarrativePattern.name == p["name"]))
        if exists:
            continue
        session.add(
            NarrativePattern(
                id=str(uuid4()),
                name=p["name"],
                pattern_type=p["pattern_type"],
                structure=p["structure"],
                performance_metadata={},
            )
        )
        created += 1
    session.flush()
    return created


def extract_pattern(blueprint: StoryBlueprint) -> dict[str, Any]:
    return {
        "hook": blueprint.hook.type,
        "template": blueprint.template,
        "ending": blueprint.ending_type,
        "has_twist": blueprint.twist is not None,
        "loop": bool((blueprint.loop or {}).get("enabled")),
        "cta_objective": blueprint.cta.objective,
    }


def find_matching_pattern(session: Session, story_type: str | None) -> NarrativePattern | None:
    if not story_type:
        return None
    return session.scalar(
        select(NarrativePattern).where(NarrativePattern.pattern_type == story_type).limit(1)
    )


def save_pattern_from_blueprint(
    session: Session, blueprint: StoryBlueprint, *, name: str
) -> NarrativePattern:
    row = NarrativePattern(
        id=str(uuid4()),
        name=name,
        pattern_type=blueprint.template,
        structure=extract_pattern(blueprint),
        performance_metadata={},
    )
    session.add(row)
    session.flush()
    return row
