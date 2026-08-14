from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from orchestration_engine.schemas import TrendOpportunityIn


def assemble_creative_context(
    session: Session,
    *,
    opportunity: TrendOpportunityIn,
    mechanism: dict[str, Any],
    character_slug: str,
    platform: str,
) -> dict[str, Any]:
    """Build CreativeContext from brand/character/learning — does not invent story."""
    character_info: dict[str, Any] = {"slug": character_slug}
    try:
        from asset_engine.characters import CharacterRegistry

        reg = CharacterRegistry(session)
        ch = reg.by_slug(character_slug)
        if ch:
            character_info = reg.to_adaptation_dict(ch) if hasattr(reg, "to_adaptation_dict") else {
                "slug": character_slug,
                "id": getattr(ch, "id", None),
                "name": getattr(ch, "name", character_slug),
            }
    except Exception:  # noqa: BLE001
        pass

    optimization_profile = None
    try:
        from learning_engine.service import LearningService

        brief = LearningService(session).brief(
            character=character_slug,
            platform=platform if platform != "instagram_reels" else "instagram",
            persist=False,
        )
        optimization_profile = brief.get("brief")
    except Exception:  # noqa: BLE001
        optimization_profile = None

    return {
        "brand": {"name": "amp", "voice": "in-universe character-led"},
        "character": character_info,
        "audience": opportunity.audience,
        "platform": platform,
        "objective": "growth",
        "trend": opportunity.model_dump(),
        "trend_mechanism": mechanism,
        "historical_learning": {
            "optimization_brief": optimization_profile,
            "note": "Association-based; not causal",
        },
        "creative_constraints": {
            "never_copy_surface_trend": True,
            "operate_on_mechanism": True,
            "max_duration_sec": 45,
            "aspect_ratio": "9:16",
        },
        "optimization_profile": optimization_profile,
    }
