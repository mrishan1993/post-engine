from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from asset_engine.registry import AssetRegistry
from asset_engine.schemas import CharacterCanonical
from db.models import Character, CharacterMemory, CharacterVersion, VoiceProfile


class CharacterRegistry:
    """Character identity + versioning + canon (separate from representation assets)."""

    def __init__(self, session: Session):
        self.session = session
        self.assets = AssetRegistry(session)

    def create(
        self,
        *,
        slug: str,
        name: str,
        canonical: CharacterCanonical | dict[str, Any],
        description: str | None = None,
        universe_id: str | None = None,
        tags: list[str] | None = None,
        status: str = "draft",
    ) -> Character:
        if self.by_slug(slug):
            raise ValueError(f"character slug already exists: {slug}")
        data = (
            canonical.model_dump()
            if isinstance(canonical, CharacterCanonical)
            else CharacterCanonical.model_validate(canonical).model_dump()
        )
        char = Character(
            id=str(uuid4()),
            slug=slug,
            name=name,
            description=description,
            universe_id=universe_id,
            canonical_data=data,
            current_version=1,
            status=status,
            tags=tags or [],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(char)
        self.session.flush()
        self.session.add(
            CharacterVersion(
                id=str(uuid4()),
                character_id=char.id,
                version=1,
                canonical_data=data,
                change_log="initial",
            )
        )
        self.session.flush()
        get_bus().publish(
            EventType.CHARACTER_CREATED,
            {"character_id": char.id, "slug": slug, "version": 1, "status": status},
            producer="asset-engine",
        )
        return char

    def by_slug(self, slug: str) -> Character | None:
        return self.session.scalar(select(Character).where(Character.slug == slug))

    def get(self, character_id: str) -> Character | None:
        return self.session.get(Character, character_id)

    def get_version(self, character_id: str, version: int) -> CharacterVersion | None:
        return self.session.scalar(
            select(CharacterVersion).where(
                CharacterVersion.character_id == character_id,
                CharacterVersion.version == version,
            )
        )

    def bump_version(
        self,
        character_id: str,
        canonical: CharacterCanonical | dict[str, Any],
        *,
        change_log: str | None = None,
        activate: bool = True,
    ) -> CharacterVersion:
        char = self.get(character_id)
        if not char:
            raise ValueError(f"character {character_id} not found")
        data = (
            canonical.model_dump()
            if isinstance(canonical, CharacterCanonical)
            else CharacterCanonical.model_validate(canonical).model_dump()
        )
        new_ver = int(char.current_version) + 1
        row = CharacterVersion(
            id=str(uuid4()),
            character_id=char.id,
            version=new_ver,
            canonical_data=data,
            change_log=change_log,
        )
        self.session.add(row)
        char.canonical_data = data
        char.current_version = new_ver
        char.updated_at = datetime.now(timezone.utc)
        if activate and char.status == "draft":
            char.status = "active"
        self.session.flush()
        get_bus().publish(
            EventType.CHARACTER_VERSIONED,
            {"character_id": char.id, "slug": char.slug, "version": new_ver},
            producer="asset-engine",
        )
        return row

    def set_status(self, character_id: str, status: str) -> Character:
        char = self.get(character_id)
        if not char:
            raise ValueError(f"character {character_id} not found")
        char.status = status
        char.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return char

    def attach_reference(
        self,
        character_id: str,
        asset_id: str,
        *,
        role: str = "has_reference",
    ) -> None:
        self.assets.link(
            source_type="character",
            source_id=character_id,
            target_type="asset",
            target_id=asset_id,
            relationship_type=role,
        )

    def attach_voice(self, character_id: str, voice_profile_id: str) -> None:
        self.assets.link(
            source_type="character",
            source_id=character_id,
            target_type="voice",
            target_id=voice_profile_id,
            relationship_type="has_voice",
        )
        char = self.get(character_id)
        if char:
            data = dict(char.canonical_data or {})
            voice = dict(data.get("voice") or {})
            voice["voice_profile_id"] = voice_profile_id
            data["voice"] = voice
            char.canonical_data = data
            self.session.flush()

    def add_relationship(
        self,
        character_id: str,
        other_character_id: str,
        *,
        relation_type: str,
        strength: float = 0.5,
        description: str | None = None,
    ) -> None:
        self.assets.link(
            source_type="character",
            source_id=character_id,
            target_type="character",
            target_id=other_character_id,
            relationship_type=relation_type,
            metadata={"strength": strength, "description": description},
        )

    def add_memory(
        self,
        character_id: str,
        *,
        episode_key: str,
        memory_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> CharacterMemory:
        row = CharacterMemory(
            id=str(uuid4()),
            character_id=character_id,
            episode_key=episode_key,
            memory_text=memory_text,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def memories(self, character_id: str, limit: int = 50) -> list[CharacterMemory]:
        return list(
            self.session.scalars(
                select(CharacterMemory)
                .where(CharacterMemory.character_id == character_id)
                .order_by(CharacterMemory.created_at.asc())
                .limit(limit)
            ).all()
        )

    def create_voice_profile(
        self,
        *,
        slug: str,
        name: str,
        characteristics: dict[str, Any] | None = None,
        provider_mappings: dict[str, Any] | None = None,
        status: str = "active",
    ) -> VoiceProfile:
        existing = self.session.scalar(select(VoiceProfile).where(VoiceProfile.slug == slug))
        if existing:
            return existing
        row = VoiceProfile(
            id=str(uuid4()),
            slug=slug,
            name=name,
            characteristics=characteristics or {},
            provider_mappings=provider_mappings or {},
            status=status,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_characters(self, *, status: str | None = None) -> list[Character]:
        q = select(Character).order_by(Character.name.asc())
        if status:
            q = q.where(Character.status == status)
        return list(self.session.scalars(q).all())

    def to_adaptation_dict(self, character: Character) -> dict[str, Any]:
        """Shape used by strategy/probability character adaptation."""
        data = character.canonical_data or {}
        personality = data.get("personality") or {}
        voice = data.get("voice") or {}
        return {
            "slug": character.slug,
            "name": character.name,
            "voice": voice.get("description") or voice.get("characteristics") or "neutral",
            "traits": personality.get("traits") or [],
            "character_id": character.id,
            "character_version": character.current_version,
            "canonical_data": data,
        }
