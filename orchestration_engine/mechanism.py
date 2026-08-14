from __future__ import annotations

from typing import Any

from orchestration_engine.schemas import TrendOpportunityIn


MECHANISM_LIBRARY: dict[str, dict[str, Any]] = {
    "unexpected_reveal": {
        "mechanism": "unexpected_reveal",
        "hook_pattern": "open_loop",
        "narrative_pattern": "setup → escalation → reveal",
        "emotional_pattern": "curiosity → surprise",
        "editing_pattern": "fast_setup → pause → reveal",
        "recommended_duration": "8-15s",
    },
    "curiosity_gap": {
        "mechanism": "curiosity_gap",
        "hook_pattern": "open_loop",
        "narrative_pattern": "question → withhold → payoff",
        "emotional_pattern": "curiosity → relief",
        "editing_pattern": "hook_text → withhold → answer",
        "recommended_duration": "12-25s",
    },
    "transformation": {
        "mechanism": "transformation",
        "hook_pattern": "before_after",
        "narrative_pattern": "before → process → after",
        "emotional_pattern": "anticipation → satisfaction",
        "editing_pattern": "split_or_cut_transform",
        "recommended_duration": "10-20s",
    },
    "relatability": {
        "mechanism": "relatability",
        "hook_pattern": "recognition",
        "narrative_pattern": "situation → recognition → punchline",
        "emotional_pattern": "empathy → amusement",
        "editing_pattern": "quick_cuts_reaction",
        "recommended_duration": "12-28s",
    },
    "humor": {
        "mechanism": "humor",
        "hook_pattern": "setup_punchline",
        "narrative_pattern": "setup → misdirect → punchline",
        "emotional_pattern": "anticipation → laughter",
        "editing_pattern": "timing_pause_punch",
        "recommended_duration": "8-18s",
    },
    "shock": {
        "mechanism": "shock",
        "hook_pattern": "pattern_interrupt",
        "narrative_pattern": "normal → interrupt → reaction",
        "emotional_pattern": "calm → shock",
        "editing_pattern": "smash_cut",
        "recommended_duration": "6-12s",
    },
}


def _normalize_key(raw: str | None) -> str:
    if not raw:
        return "curiosity_gap"
    key = raw.lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "surprise_reveal": "unexpected_reveal",
        "reveal": "unexpected_reveal",
        "unexpected": "unexpected_reveal",
        "curiosity": "curiosity_gap",
        "open_loop": "curiosity_gap",
        "before_after": "transformation",
        "transform": "transformation",
        "relatable": "relatability",
        "funny": "humor",
        "comedy": "humor",
        "pattern_interrupt": "shock",
    }
    key = aliases.get(key, key)
    for known in MECHANISM_LIBRARY:
        if known in key or key in known:
            return known
    return "curiosity_gap"


def extract_mechanism(opportunity: TrendOpportunityIn) -> dict[str, Any]:
    """Surface trend → underlying viral mechanism (never copy the surface)."""
    raw = opportunity.viral_mechanism or opportunity.pattern_key or opportunity.title or ""
    key = _normalize_key(str(raw))
    base = dict(MECHANISM_LIBRARY[key])
    base["source_signal"] = opportunity.viral_mechanism or opportunity.pattern_key
    base["note"] = "Operate on mechanism, not surface audio/dance/meme copy"
    base["surface"] = {
        "audio": opportunity.audio,
        "format": opportunity.format,
        "title": opportunity.title,
    }
    return base
