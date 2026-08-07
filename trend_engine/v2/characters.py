from __future__ import annotations

from typing import Any


def adapt_to_characters(
    opportunity: dict[str, Any],
    characters: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Map a viral pattern onto owned AI characters → distinct brief seeds."""
    adapted: list[dict[str, Any]] = []
    hook = opportunity.get("hook") or "Something strange happened..."
    emotion = opportunity.get("emotion") or "curiosity"
    story = opportunity.get("story_pattern") or "linear"
    for char in characters[:limit]:
        adapted.append(
            {
                "character_slug": char.get("slug"),
                "character_name": char.get("name"),
                "voice": char.get("voice"),
                "traits": char.get("traits") or [],
                "opening_line": _opening_for(char, hook, emotion, story),
                "brief_angle": _angle_for(char, opportunity),
            }
        )
    return adapted


def _opening_for(char: dict[str, Any], hook: str, emotion: str, story: str) -> str:
    name = char.get("name") or "Character"
    if story == "pov":
        return f"POV — {name}: {hook}"
    if emotion == "fear":
        return f"{name} whispers: {hook}"
    if emotion == "joy":
        return f"{name} sings: {hook}"
    return f"{name}: {hook}"


def _angle_for(char: dict[str, Any], opportunity: dict[str, Any]) -> str:
    return (
        f"Adapt '{opportunity.get('trend')}' for {char.get('name')} "
        f"using {opportunity.get('story_pattern')} structure, "
        f"{opportunity.get('audio')} audio, "
        f"targeting {opportunity.get('target_audience')}."
    )
