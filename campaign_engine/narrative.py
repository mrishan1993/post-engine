from __future__ import annotations

from typing import Any


DEFAULT_JOURNEY = [
    "stranger",
    "viewer",
    "interested",
    "follower",
    "returning_viewer",
    "community_member",
    "advocate",
]

NARRATIVE_ARC = [
    "introduction",
    "setup",
    "escalation",
    "reveal",
    "finale",
]

AUDIENCE_ARC = [
    "discovery",
    "curiosity",
    "relationship",
    "community",
    "conversion",
]


def decompose_episodes(
    *,
    count: int,
    character_slug: str,
    series_name: str,
    premise: str | None,
    platforms: list[str],
) -> list[dict[str, Any]]:
    """Create ordered episode skeletons with narrative + audience roles."""
    n = max(3, min(count, 15))
    platform = platforms[0] if platforms else "instagram"
    out: list[dict[str, Any]] = []
    for i in range(1, n + 1):
        if i == 1:
            narr, aud = "introduction", "discovery"
        elif i == n:
            narr, aud = "finale", "community"
        elif i == 2:
            narr, aud = "setup", "curiosity"
        elif i == n - 1:
            narr, aud = "payoff", "relationship"
        elif i == max(3, n // 2):
            narr, aud = "reveal", "curiosity"
        else:
            narr, aud = "escalation", "relationship"
        out.append(
            {
                "episode_number": i,
                "title": f"{series_name} — Ep {i}",
                "objective": f"Advance {narr} for {character_slug}",
                "premise": premise or f"{character_slug} continues the series premise",
                "hook": _hook(narr, character_slug, i),
                "narrative_role": narr,
                "audience_role": aud,
                "platform": platform,
                "cta": "Follow for Part 2" if i < n else "What should happen next?",
                "continuity_requirements": {
                    "character_slug": character_slug,
                    "must_respect_prior_facts": True,
                    "episode_number": i,
                },
            }
        )
    return out


def cross_platform_adaptations(core: dict[str, Any], platforms: list[str]) -> list[dict[str, Any]]:
    """Same core idea → platform-specific executions (not blind cross-post)."""
    adaptations = []
    for p in platforms:
        duration = {"instagram": 12, "tiktok": 15, "youtube": 45}.get(p, 12)
        adaptations.append(
            {
                "platform": p,
                "format": "short" if p == "youtube" else "reel",
                "duration_sec": duration,
                "hook": core.get("hook"),
                "title": f"{core.get('title')} ({p})",
                "adaptation_note": "platform-native execution of shared campaign idea",
            }
        )
    return adaptations


def _hook(role: str, character: str, n: int) -> str:
    hooks = {
        "introduction": f"Meet {character} — you won't expect this.",
        "setup": f"{character} thinks this will be normal…",
        "escalation": f"It gets worse for {character}.",
        "reveal": f"Wait — {character} just figured it out.",
        "payoff": f"This is why {character} did all that.",
        "finale": f"The end of this chapter for {character}.",
        "cliffhanger": f"{character} freezes. What now?",
    }
    return hooks.get(role, f"{character} — Episode {n}")
