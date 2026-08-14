from __future__ import annotations

from typing import Any


def init_continuity(*, character_slug: str, campaign_name: str) -> dict[str, Any]:
    return {
        "character": {
            "slug": character_slug,
            "starting_state": "introduced",
            "current_state": "introduced",
            "traits": [],
            "relationships": [],
            "goals": [],
            "conflicts": [],
            "unresolved_threads": [],
        },
        "story_facts": [],
        "running_jokes": [],
        "locations": [],
        "campaign_name": campaign_name,
    }


def apply_episode_to_continuity(
    continuity: dict[str, Any],
    *,
    episode_number: int,
    premise: str | None,
    narrative_role: str | None,
    facts: list[str] | None = None,
) -> dict[str, Any]:
    cont = dict(continuity or {})
    character = dict(cont.get("character") or {})
    facts_list = list(cont.get("story_facts") or [])
    for f in facts or []:
        if f not in facts_list:
            facts_list.append(f)
    if premise:
        fact = f"Ep{episode_number}: {premise}"
        if fact not in facts_list:
            facts_list.append(fact)
    if narrative_role == "cliffhanger":
        threads = list(character.get("unresolved_threads") or [])
        threads.append(f"cliffhanger_after_ep_{episode_number}")
        character["unresolved_threads"] = threads
    if narrative_role == "finale":
        character["unresolved_threads"] = []
        character["current_state"] = "arc_complete"
    elif narrative_role in {"reveal", "payoff"}:
        character["current_state"] = "developed"
    cont["character"] = character
    cont["story_facts"] = facts_list
    return cont


def validate_continuity(
    continuity: dict[str, Any],
    *,
    proposed_premise: str,
) -> list[str]:
    """Soft checks — return warnings, do not hard-fail V1."""
    warnings: list[str] = []
    facts = " ".join(continuity.get("story_facts") or []).lower()
    premise = proposed_premise.lower()
    # Naive contradiction: phone lost then used
    if "loses phone" in facts or "lost phone" in facts:
        if "uses phone" in premise or "calls on phone" in premise:
            warnings.append("Continuity risk: phone was lost but premise uses phone")
    return warnings
