from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from asset_engine.characters import CharacterRegistry
from asset_engine.registry import PRODUCTION_STATUSES, AssetRegistry
from asset_engine.schemas import GenerationContext, SceneRequest
from db.models import Asset, CreativeStyle, Universe, VoiceProfile


def resolve_generation_context(
    session: Session,
    request: SceneRequest | dict[str, Any],
) -> GenerationContext:
    """
    Asset Resolution Engine — answer: what assets do I need for this scene?

    Returns a complete generation context package so generators need not query
    multiple stores.
    """
    req = request if isinstance(request, SceneRequest) else SceneRequest.model_validate(request)
    chars = CharacterRegistry(session)
    assets = AssetRegistry(session)

    character = None
    if req.character_id:
        character = chars.get(req.character_id)
    elif req.character_slug:
        character = chars.by_slug(req.character_slug)

    if not character:
        raise ValueError("character_id or character_slug required and must exist")

    version = req.character_version or character.current_version
    ver_row = chars.get_version(character.id, version)
    canonical = (ver_row.canonical_data if ver_row else character.canonical_data) or {}

    # Collect linked reference assets and rank them
    refs_rels = assets.relations(
        source_type="character", source_id=character.id, relationship_type="has_reference"
    )
    # also accept role-specific relation types
    for role in ("face_reference", "full_body_reference", "expression_reference"):
        refs_rels.extend(
            assets.relations(source_type="character", source_id=character.id, relationship_type=role)
        )

    scored_refs: list[tuple[float, Asset, str]] = []
    seen: set[str] = set()
    for rel in refs_rels:
        if rel.target_id in seen:
            continue
        seen.add(rel.target_id)
        asset = assets.get(rel.target_id)
        if not asset or asset.status not in PRODUCTION_STATUSES | {"draft"}:
            # allow draft in Phase-0 for stub refs; prefer production
            if not asset:
                continue
        score = assets.score_asset(asset, emotion=req.emotion, style=req.style)
        if asset.status in PRODUCTION_STATUSES:
            score += 5
        scored_refs.append((score, asset, rel.relationship_type))
    scored_refs.sort(key=lambda x: x[0], reverse=True)

    references = [
        {
            "asset_id": a.id,
            "name": a.name,
            "type": a.asset_type,
            "role": role,
            "uri": a.storage_uri,
            "score": score,
            "provider": a.provider,
            "version": a.version,
        }
        for score, a, role in scored_refs
    ]

    # Voice
    voice_payload = None
    voice_id = (canonical.get("voice") or {}).get("voice_profile_id")
    if not voice_id:
        voice_rels = assets.relations(
            source_type="character", source_id=character.id, relationship_type="has_voice"
        )
        if voice_rels:
            voice_id = voice_rels[0].target_id
    if voice_id:
        vp = session.get(VoiceProfile, voice_id)
        if vp:
            voice_payload = {
                "voice_profile_id": vp.id,
                "slug": vp.slug,
                "name": vp.name,
                "characteristics": vp.characteristics,
                "provider_mappings": vp.provider_mappings,
            }

    # Location / prop / style via tag search
    location_payload = None
    if req.location:
        locs = assets.search(
            query=req.location,
            asset_type="location",
            status_in=PRODUCTION_STATUSES | {"draft", "approved", "active"},
            limit=5,
        )
        if locs:
            best = max(locs, key=lambda a: assets.score_asset(a, emotion=req.emotion, style=req.style))
            location_payload = {
                "id": best.id,
                "name": best.name,
                "uri": best.storage_uri,
                "tags": best.tags,
                "metadata": best.metadata_json,
            }

    props: list[dict[str, Any]] = []
    if req.prop:
        found = assets.search(
            query=req.prop,
            asset_type="prop",
            status_in=PRODUCTION_STATUSES | {"draft", "approved", "active"},
            limit=5,
        )
        for p in found[:3]:
            props.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "uri": p.storage_uri,
                    "score": assets.score_asset(p, emotion=req.emotion),
                }
            )

    style_payload = None
    style_slug = req.style or (canonical.get("visual_style") or {}).get("style_id")
    if style_slug:
        style = session.scalar(select(CreativeStyle).where(CreativeStyle.slug == style_slug))
        if style:
            style_payload = {
                "id": style.id,
                "slug": style.slug,
                "name": style.name,
                "configuration": style.configuration,
            }

    world_payload = None
    if character.universe_id:
        universe = session.get(Universe, character.universe_id)
        if universe:
            world_payload = {
                "id": universe.id,
                "slug": universe.slug,
                "name": universe.name,
                "rules": universe.rules,
            }

    memory = [
        {"episode_key": m.episode_key, "text": m.memory_text}
        for m in chars.memories(character.id, limit=20)
    ]

    selection_scores = {r["asset_id"]: r["score"] for r in references}

    ctx = GenerationContext(
        character={
            "id": character.id,
            "slug": character.slug,
            "name": character.name,
            "version": version,
            "identity": canonical.get("identity"),
            "personality": canonical.get("personality"),
            "appearance": canonical.get("appearance"),
            "behavioral_rules": canonical.get("behavioral_rules"),
            "canon": canonical.get("canon"),
            "prompt_instructions": canonical.get("prompt_instructions"),
            "status": character.status,
        },
        references=references,
        location=location_payload,
        props=props,
        style=style_payload,
        voice=voice_payload,
        world=world_payload,
        memory=memory,
        constraints={
            "platform": req.platform,
            "duration_sec": req.duration_sec,
            "emotion": req.emotion,
            "action": req.action,
            "camera": req.camera,
            "forbidden": (canonical.get("canon") or {}).get("forbidden") or [],
            "immutable": (canonical.get("canon") or {}).get("immutable") or [],
        },
        selection_scores=selection_scores,
    )

    get_bus().publish(
        EventType.GENERATION_CONTEXT_RESOLVED,
        {
            "character_id": character.id,
            "character_version": version,
            "reference_count": len(references),
            "platform": req.platform,
        },
        producer="asset-engine",
    )
    return ctx
