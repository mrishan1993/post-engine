from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_engine.characters import CharacterRegistry
from asset_engine.registry import AssetRegistry
from asset_engine.schemas import CharacterCanonical
from db.models import CreativeStyle, Universe

V2_CONFIG = Path(__file__).resolve().parent.parent / "trend_engine" / "config" / "v2.yaml"
RIGS = Path(__file__).resolve().parent.parent / "rigs"


def seed_from_v2_config(session: Session) -> dict[str, Any]:
    """Seed universes, styles, voices, characters, and reference assets from existing config/rigs."""
    chars = CharacterRegistry(session)
    assets = AssetRegistry(session)
    created = {"characters": 0, "assets": 0, "styles": 0, "voices": 0, "universes": 0}

    with V2_CONFIG.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    # Universes / styles
    universes = {
        "kids_rhymes": _ensure_universe(
            session, "kids_universe", "Kids Rhyme World", {"tone": "warm playful"}
        ),
        "horror_narration": _ensure_universe(
            session, "haunted_tales", "Haunted Tales", {"tone": "atmospheric no gore"}
        ),
    }
    created["universes"] = 2

    styles = {
        "kids_bright": _ensure_style(
            session,
            "kids_bright",
            "Bright Kids 3D",
            {
                "visual": {"lighting": "high_key", "camera": "friendly"},
                "color": {"palette": ["sky_blue", "yellow", "soft_green"]},
                "editing": {"pacing": "medium"},
            },
        ),
        "cinematic_horror": _ensure_style(
            session,
            "cinematic_horror",
            "Dark Cinematic Horror",
            {
                "visual": {"lighting": "low_key", "contrast": "high", "camera": "cinematic"},
                "color": {"palette": ["dark_blue", "gray", "muted_red"]},
                "editing": {"pacing": "fast"},
            },
        ),
    }
    created["styles"] = len(styles)

    # Location assets
    for name, tags, utype in (
        ("Haunted School", ["horror", "school", "dark", "scared"], "horror_narration"),
        ("Color Classroom", ["kids", "bright", "colors", "joy"], "kids_rhymes"),
        ("Flashlight", ["prop", "horror", "scared"], None),
    ):
        asset_type = "prop" if "prop" in tags else "location"
        existing = assets.search(query=name, asset_type=asset_type, limit=1)
        if not existing:
            assets.create(
                asset_type=asset_type,
                name=name,
                tags=tags,
                status="active",
                provider="seed",
                metadata={"seed": True, "vertical": utype},
            )
            created["assets"] += 1

    # Characters from v2.yaml
    for vertical, char_list in (cfg.get("characters") or {}).items():
        universe = universes.get(vertical)
        style = styles["kids_bright" if vertical == "kids_rhymes" else "cinematic_horror"]
        for c in char_list:
            slug = c["slug"]
            if chars.by_slug(slug):
                continue
            voice = chars.create_voice_profile(
                slug=f"voice_{slug}",
                name=f"{c['name']} Voice",
                characteristics={"description": c.get("voice"), "traits": c.get("traits")},
                provider_mappings={
                    "elevenlabs": None,
                    "stub": f"stub_{slug}",
                    "provider_a": f"provider_a_voice_{slug}",
                    "provider_b": f"provider_b_voice_{slug}",
                },
                status="active",
            )
            created["voices"] += 1
            canonical = CharacterCanonical(
                identity={"species": "character", "vertical": vertical},
                personality={"traits": c.get("traits") or []},
                appearance={},
                behavioral_rules=[],
                voice={
                    "voice_profile_id": voice.id,
                    "description": c.get("voice"),
                },
                visual_style={"style_id": style.slug},
                prompt_instructions=[
                    f"Stay in character as {c['name']}.",
                    f"Voice: {c.get('voice')}.",
                ],
            )
            char = chars.create(
                slug=slug,
                name=c["name"],
                canonical=canonical,
                description=f"{c['name']} for {vertical}",
                universe_id=universe.id if universe else None,
                tags=[vertical, *(c.get("traits") or [])],
                status="active",
            )
            chars.attach_voice(char.id, voice.id)
            created["characters"] += 1

            # Attach rig reference images when present
            rig_parts = RIGS / ("kids_rhymes" if vertical == "kids_rhymes" else "horror_narration")
            if vertical == "kids_rhymes":
                for fname, role, atype in (
                    ("character_parts/body.png", "full_body_reference", "character_reference"),
                    ("character_parts/mouth_open.png", "expression_reference", "face_reference"),
                    ("character_parts/mouth_closed.png", "expression_reference", "face_reference"),
                    ("backgrounds/default.png", "has_reference", "location"),
                ):
                    path = rig_parts / fname
                    if path.exists():
                        asset = assets.register_file(
                            path,
                            asset_type=atype,
                            name=f"{slug}_{path.stem}",
                            tags=[slug, vertical, role, "kids"],
                            status="active",
                        )
                        chars.attach_reference(char.id, asset.id, role=role)
                        created["assets"] += 1
            else:
                # Placeholder generation-reference asset (no image yet)
                asset = assets.create(
                    asset_type="character_reference",
                    name=f"{slug}_concept",
                    tags=[slug, vertical, "horror", "scared"],
                    status="active",
                    provider="seed",
                    metadata={"note": "Replace with real reference sheet"},
                    quality={"character_similarity": 0.7, "generation_quality": 0.7},
                )
                chars.attach_reference(char.id, asset.id, role="has_reference")
                created["assets"] += 1

            # Seed a memory beat
            chars.add_memory(
                char.id,
                episode_key="pilot",
                memory_text=f"{c['name']} appeared in the first story of {vertical}.",
            )

    # Relationship example
    ghost = chars.by_slug("ghost_kid")
    doll = chars.by_slug("haunted_doll")
    if ghost and doll:
        existing = assets.relations(
            source_type="character", source_id=ghost.id, relationship_type="knows_character"
        )
        if not any(r.target_id == doll.id for r in existing):
            chars.add_relationship(
                ghost.id,
                doll.id,
                relation_type="knows_character",
                strength=0.6,
                description="Uneasy alliance in the haunted school",
            )

    return created


def _ensure_universe(session: Session, slug: str, name: str, rules: dict) -> Universe:
    row = session.scalar(select(Universe).where(Universe.slug == slug))
    if row:
        return row
    row = Universe(
        id=str(uuid4()),
        slug=slug,
        name=name,
        rules=rules,
        status="active",
    )
    session.add(row)
    session.flush()
    return row


def _ensure_style(session: Session, slug: str, name: str, configuration: dict) -> CreativeStyle:
    row = session.scalar(select(CreativeStyle).where(CreativeStyle.slug == slug))
    if row:
        return row
    row = CreativeStyle(
        id=str(uuid4()),
        slug=slug,
        name=name,
        configuration=configuration,
        status="active",
    )
    session.add(row)
    session.flush()
    return row
