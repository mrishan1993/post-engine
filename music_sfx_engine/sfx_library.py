from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from config.settings import get_settings
from db.models import AudioArtifact, SfxLibraryAsset
from music_sfx_engine.schemas import SfxSpec

SEED_SFX: list[dict[str, Any]] = [
    {"category": "footsteps", "subtype": "wood", "name": "soft_wood_steps", "duration_sec": 0.4, "intensity": 0.5, "tags": ["horror", "footsteps", "wood"]},
    {"category": "doors", "subtype": "creak", "name": "old_door_creak", "duration_sec": 1.2, "intensity": 0.7, "tags": ["horror", "door", "wood", "old"]},
    {"category": "impacts", "subtype": "hit", "name": "heavy_impact", "duration_sec": 0.5, "intensity": 1.0, "tags": ["horror", "impact", "hit"]},
    {"category": "transitions", "subtype": "whoosh", "name": "soft_whoosh", "duration_sec": 0.35, "intensity": 0.45, "tags": ["transition", "whoosh"]},
    {"category": "transitions", "subtype": "stinger", "name": "cta_stinger", "duration_sec": 0.8, "intensity": 0.8, "tags": ["cta", "stinger"]},
    {"category": "nature", "subtype": "wind", "name": "distant_wind", "duration_sec": 3.0, "intensity": 0.3, "tags": ["ambience", "wind", "nature"]},
    {"category": "horror", "subtype": "riser", "name": "tension_riser", "duration_sec": 2.0, "intensity": 0.75, "tags": ["horror", "riser", "tension"]},
    {"category": "human", "subtype": "breath", "name": "sharp_breath", "duration_sec": 0.6, "intensity": 0.55, "tags": ["human", "breath", "horror"]},
    {"category": "technology", "subtype": "phone", "name": "phone_buzz", "duration_sec": 0.9, "intensity": 0.6, "tags": ["phone", "technology"]},
    {"category": "vehicles", "subtype": "car", "name": "distant_car", "duration_sec": 2.5, "intensity": 0.4, "tags": ["car", "vehicles"]},
]

TYPE_ALIASES: dict[str, tuple[str, str | None]] = {
    "footsteps": ("footsteps", None),
    "door_creak": ("doors", "creak"),
    "door": ("doors", None),
    "impact": ("impacts", "hit"),
    "impact_soft": ("impacts", "hit"),
    "whoosh": ("transitions", "whoosh"),
    "stinger": ("transitions", "stinger"),
    "wind": ("nature", "wind"),
    "riser": ("horror", "riser"),
    "phone": ("technology", "phone"),
}


def seed_sfx_library(session: Session) -> int:
    existing = session.scalar(select(SfxLibraryAsset).limit(1))
    if existing:
        return 0
    settings = get_settings()
    root = Path(settings.storage_root) / "library" / "sfx"
    root.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in SEED_SFX:
        aid = str(uuid4())
        path = root / f"{item['category']}_{item['subtype'] or 'base'}_{aid[:8]}.wav"
        payload = {"stub": True, "library": True, **item, "id": aid}
        path.write_bytes(b"AMP_SFX_STUB\n" + json.dumps(payload).encode("utf-8"))
        path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")
        session.add(
            SfxLibraryAsset(
                id=aid,
                category=item["category"],
                subtype=item.get("subtype"),
                name=item["name"],
                duration_sec=item["duration_sec"],
                intensity=item["intensity"],
                tags=list(item.get("tags") or []),
                storage_uri=str(path),
                licensed=True,
                reuse_count=0,
                metadata_json={"seed": True},
                created_at=datetime.now(timezone.utc),
            )
        )
        count += 1
    session.flush()
    return count


def search_sfx(
    session: Session,
    *,
    query: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[SfxLibraryAsset]:
    rows = list(session.scalars(select(SfxLibraryAsset)).all())
    scored: list[tuple[float, SfxLibraryAsset]] = []
    q = (query or "").lower()
    tagset = {t.lower() for t in (tags or [])}
    for row in rows:
        if category and row.category != category and row.subtype != category:
            continue
        score = 0.0
        blob = f"{row.name} {row.category} {row.subtype or ''} {' '.join(row.tags or [])}".lower()
        if q and q in blob:
            score += 2.0
        if q and any(tok in blob for tok in q.replace("_", " ").split()):
            score += 1.0
        if tagset:
            overlap = tagset & {t.lower() for t in (row.tags or [])}
            score += 0.5 * len(overlap)
        if not q and not tagset:
            score = 1.0
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: (-x[0], x[1].reuse_count))
    return [r for _, r in scored[:limit]]


def resolve_sfx(
    session: Session,
    specs: list[SfxSpec] | list[dict[str, Any]],
) -> list[AudioArtifact]:
    """Library-first SFX resolution; stub-generate only if no match."""
    seed_sfx_library(session)
    artifacts: list[AudioArtifact] = []
    for raw in specs:
        spec = raw if isinstance(raw, SfxSpec) else SfxSpec.model_validate(raw)
        cat, sub = TYPE_ALIASES.get(spec.type, (spec.type, None))
        matches = search_sfx(
            session,
            query=spec.type,
            category=cat,
            tags=spec.tags or ([sub] if sub else []),
            limit=5,
        )
        chosen = None
        if matches and spec.source_preference != "generate":
            # Prefer subtype match
            for m in matches:
                if sub and m.subtype == sub:
                    chosen = m
                    break
            chosen = chosen or matches[0]

        if chosen:
            chosen.reuse_count = int(chosen.reuse_count or 0) + 1
            art = AudioArtifact(
                id=str(uuid4()),
                generation_job_id=None,
                artifact_type="sfx",
                storage_uri=chosen.storage_uri or "",
                mime_type="audio/wav",
                duration_sec=float(chosen.duration_sec or spec.duration_sec),
                sample_rate=44100,
                channels=1,
                loudness_lufs=-18.0,
                true_peak_db=-2.0,
                sfx_library_id=chosen.id,
                provider="sfx_library",
                model="library",
                metadata_json={
                    "sfx_spec_id": spec.id,
                    "type": spec.type,
                    "start_sec": spec.start_sec,
                    "intensity": spec.intensity,
                    "source": "library",
                    "visual_event": spec.visual_event,
                },
                lineage={"sfx_library_id": chosen.id},
            )
            session.add(art)
            artifacts.append(art)
            get_bus().publish(
                EventType.SFX_SELECTED,
                {
                    "artifact_id": art.id,
                    "sfx_library_id": chosen.id,
                    "type": spec.type,
                    "start_sec": spec.start_sec,
                },
                producer="music-sfx-engine",
            )
        elif spec.source_preference != "library_only":
            art = _generate_stub_sfx(session, spec)
            artifacts.append(art)
        else:
            get_bus().publish(
                EventType.SFX_REQUESTED,
                {"type": spec.type, "status": "unresolved"},
                producer="music-sfx-engine",
            )
    session.flush()
    return artifacts


def _generate_stub_sfx(session: Session, spec: SfxSpec) -> AudioArtifact:
    settings = get_settings()
    root = Path(settings.storage_root) / "generated" / "sfx"
    root.mkdir(parents=True, exist_ok=True)
    aid = str(uuid4())
    path = root / f"{spec.type}_{aid[:8]}.wav"
    payload = {
        "stub": True,
        "generated": True,
        "type": spec.type,
        "duration_sec": spec.duration_sec,
        "sample_rate": 44100,
        "channels": 1,
        "loudness_lufs": -16.0,
        "true_peak_db": -1.5,
    }
    path.write_bytes(b"AMP_SFX_STUB\n" + json.dumps(payload).encode("utf-8"))
    path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")
    art = AudioArtifact(
        id=aid,
        artifact_type="sfx",
        storage_uri=str(path),
        mime_type="audio/wav",
        duration_sec=spec.duration_sec,
        sample_rate=44100,
        channels=1,
        loudness_lufs=-16.0,
        true_peak_db=-1.5,
        provider="sfx_stub",
        model="sfx-gen-stub-1",
        metadata_json={
            "sfx_spec_id": spec.id,
            "type": spec.type,
            "start_sec": spec.start_sec,
            "intensity": spec.intensity,
            "source": "generated",
            "visual_event": spec.visual_event,
        },
        lineage={"source": "generated_fallback"},
    )
    session.add(art)
    get_bus().publish(
        EventType.SFX_REQUESTED,
        {"artifact_id": art.id, "type": spec.type, "status": "generated"},
        producer="music-sfx-engine",
    )
    return art
