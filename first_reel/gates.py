from __future__ import annotations

from typing import Any


REQUIRED_LINEAGE = [
    "content_id",
    "trend_id",
    "strategy_id",
    "campaign_id",
    "creative_id",
    "generation_run_id",
    "assembly_run_id",
    "qa_run_id",
    "publication_id",
]


def check_trend_freshness(
    opportunity: dict[str, Any],
    *,
    min_freshness: float = 0.45,
) -> tuple[bool, str]:
    freshness = float(opportunity.get("freshness_score") or 0)
    stage = str(opportunity.get("trend_stage") or "").lower()
    if stage in {"saturated", "declining", "dead"}:
        return False, f"trend_stage={stage}"
    if freshness < min_freshness:
        return False, f"freshness={freshness}<{min_freshness}"
    return True, "ok"


def check_first_frame_hook(creative: dict[str, Any]) -> tuple[bool, list[str]]:
    """Hook must be understandable without audio on first frame."""
    issues: list[str] = []
    hook = (creative.get("hook") or "").strip()
    if not hook:
        issues.append("missing_hook")
    if hook and "POV" not in hook.upper() and len(hook) < 8:
        issues.append("hook_too_weak")
    shots = creative.get("shots") or []
    if shots:
        first = shots[0]
        if not (first.get("text") or hook):
            issues.append("first_frame_no_text")
        if float(first.get("t1") or 0) > 2.0:
            issues.append("hook_window_too_long")
    return (len(issues) == 0), issues


def check_lineage(lineage: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = [k for k in REQUIRED_LINEAGE if not lineage.get(k)]
    # Allow qa_id alias
    if "qa_run_id" in missing and lineage.get("qa_id"):
        missing.remove("qa_run_id")
    if "assembly_run_id" in missing and lineage.get("assembly_id"):
        missing.remove("assembly_run_id")
    if "creative_id" in missing and lineage.get("concept_id"):
        missing.remove("creative_id")
    return (len(missing) == 0), missing


def check_audio_strategy(brief_audio: dict[str, Any] | None, lineage: dict[str, Any]) -> bool:
    audio = brief_audio or {}
    strategy = audio.get("audio_strategy") or lineage.get("audio_strategy")
    return strategy == "platform_native" and bool(
        audio.get("trend_audio", lineage.get("native_audio_pending", True))
    )
