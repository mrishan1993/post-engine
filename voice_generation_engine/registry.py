from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Character, VoiceProfile


def get_voice_profile(session: Session, voice_profile_id: str) -> VoiceProfile | None:
    row = session.get(VoiceProfile, voice_profile_id)
    if row:
        return row
    rows = list(
        session.scalars(
            select(VoiceProfile).where(VoiceProfile.id.startswith(voice_profile_id))
        ).all()
    )
    if len(rows) == 1:
        return rows[0]
    rows = list(
        session.scalars(select(VoiceProfile).where(VoiceProfile.slug == voice_profile_id)).all()
    )
    return rows[0] if len(rows) == 1 else None


def resolve_character_voice(
    session: Session,
    *,
    character_id: str | None = None,
    character_slug: str | None = None,
) -> tuple[Character | None, VoiceProfile | None]:
    char = None
    if character_id:
        char = session.get(Character, character_id)
        if not char:
            rows = list(
                session.scalars(
                    select(Character).where(Character.id.startswith(character_id))
                ).all()
            )
            char = rows[0] if len(rows) == 1 else None
    elif character_slug:
        char = session.scalar(select(Character).where(Character.slug == character_slug))

    if not char:
        return None, None
    voice_id = ((char.canonical_data or {}).get("voice") or {}).get("voice_profile_id")
    profile = get_voice_profile(session, voice_id) if voice_id else None
    return char, profile


def provider_voice_id(profile: VoiceProfile | None, provider: str) -> str:
    """Map canonical voice profile → provider-specific voice id (never invent identity)."""
    if not profile:
        return f"{provider}_default"
    mappings = profile.provider_mappings or {}
    # Prefer explicit provider key, then stub/elevenlabs aliases, then deterministic stub
    for key in (provider, "stub", "elevenlabs", "provider_a", "provider_b"):
        val = mappings.get(key)
        if val:
            return str(val)
    return f"{provider}_{profile.slug}"


def ensure_provider_mappings(profile: VoiceProfile) -> dict[str, Any]:
    mappings = dict(profile.provider_mappings or {})
    changed = False
    for pid in ("provider_a", "provider_b"):
        if not mappings.get(pid):
            mappings[pid] = f"{pid}_{profile.slug}"
            changed = True
    if changed:
        profile.provider_mappings = mappings
    return mappings


def list_voice_profiles(session: Session, *, status: str | None = "active") -> list[VoiceProfile]:
    q = select(VoiceProfile).order_by(VoiceProfile.name.asc())
    if status:
        q = q.where(VoiceProfile.status == status)
    return list(session.scalars(q).all())
