from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from asset_engine.characters import CharacterRegistry
from asset_engine.resolver import resolve_generation_context
from asset_engine.schemas import SceneRequest
from storyboard_engine.schemas import AssetRequirements, StoryboardDocument, StoryboardRequest


def resolve_assets_for_storyboard(
    session: Session,
    request: StoryboardRequest,
    *,
    location_name: str | None = None,
    emotion: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    """Resolve characters/locations/styles via Asset Engine. Never invent asset IDs."""
    char_ctx: dict[str, Any] = {}
    reg = CharacterRegistry(session)
    char = None
    for cid in request.character_ids:
        char = reg.get(cid)
        if char:
            break
    if not char:
        for slug in request.character_slugs:
            char = reg.by_slug(slug)
            if char:
                break
    if char:
        char_ctx = {
            "id": char.id,
            "slug": char.slug,
            "name": char.name,
            "version": char.current_version,
            "current_version": char.current_version,
            "canonical_data": char.canonical_data,
        }

    resolved: dict[str, Any] = {"character": char_ctx or None, "location": None, "style": None}
    availability = 0.55
    try:
        ctx = resolve_generation_context(
            session,
            SceneRequest(
                character_id=char.id if char else None,
                character_slug=char.slug if char else (request.character_slugs[0] if request.character_slugs else None),
                location=request.location_query or location_name,
                emotion=emotion or "scared",
                style=request.visual_style,
                platform=request.platform,
            ),
        )
        if ctx.character:
            resolved["character"] = {**char_ctx, **ctx.character} if char_ctx else ctx.character
            if not char_ctx and ctx.character.get("name"):
                char_ctx = {
                    "id": ctx.character.get("id"),
                    "slug": ctx.character.get("slug"),
                    "name": ctx.character.get("name"),
                    "version": ctx.character.get("version"),
                    "current_version": ctx.character.get("version"),
                }
        if ctx.location:
            resolved["location"] = ctx.location
        if ctx.style:
            resolved["style"] = ctx.style
        if ctx.props:
            resolved["props"] = ctx.props
        hits = sum(1 for k in ("character", "location", "style") if resolved.get(k))
        availability = round(0.55 + 0.15 * hits, 2)
    except Exception:  # noqa: BLE001
        availability = 0.55 if char_ctx else 0.4

    return char_ctx, resolved, min(1.0, availability)


def attach_resolved_requirements(
    doc: StoryboardDocument, resolved: dict[str, Any]
) -> AssetRequirements:
    reqs = doc.asset_requirements.model_copy(deep=True)
    if resolved.get("character") and resolved["character"].get("id"):
        cid = resolved["character"]["id"]
        if cid not in reqs.characters:
            reqs.characters = [cid, *[c for c in reqs.characters if c != cid]]
    if resolved.get("location") and resolved["location"].get("id"):
        lid = resolved["location"]["id"]
        reqs.locations = [lid]
    if resolved.get("style") and resolved["style"].get("id"):
        reqs.styles = [resolved["style"]["id"]]
    if resolved.get("props"):
        for p in resolved["props"]:
            name = p.get("name") or p.get("id")
            if name and name not in reqs.props:
                reqs.props.append(str(name))
    doc.asset_requirements = reqs
    doc.resolved_assets = resolved
    return reqs
