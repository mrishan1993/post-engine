from __future__ import annotations

from asset_engine.characters import CharacterRegistry
from asset_engine.resolver import resolve_generation_context
from asset_engine.schemas import CharacterCanonical, SceneRequest
from asset_engine.seed import seed_from_v2_config
from db.session import get_session


def test_seed_and_resolve_ghost_kid(db_url: str) -> None:
    with get_session(db_url) as session:
        result = seed_from_v2_config(session)
        assert result["characters"] >= 1

        char = CharacterRegistry(session).by_slug("ghost_kid")
        assert char is not None
        assert char.current_version == 1
        assert char.status == "active"
        assert "canon" in (char.canonical_data or {})

        ctx = resolve_generation_context(
            session,
            SceneRequest(
                character_slug="ghost_kid",
                location="Haunted School",
                emotion="scared",
                action="running",
                prop="Flashlight",
                style="cinematic_horror",
                platform="instagram_reels",
            ),
        )
        assert ctx.character["slug"] == "ghost_kid"
        assert ctx.character["version"] == 1
        assert ctx.voice is not None
        assert ctx.location is not None
        assert ctx.style is not None
        assert ctx.constraints["platform"] == "instagram_reels"
        assert ctx.memory


def test_character_versioning_is_pinned(db_url: str) -> None:
    with get_session(db_url) as session:
        reg = CharacterRegistry(session)
        char = reg.create(
            slug="ravi_test",
            name="Ravi",
            canonical=CharacterCanonical(
                identity={"age": 12},
                personality={"traits": ["curious"]},
            ),
            status="active",
        )
        v1 = char.current_version
        reg.bump_version(
            char.id,
            CharacterCanonical(
                identity={"age": 12},
                personality={"traits": ["curious", "brave"]},
            ),
            change_log="added brave",
        )
        assert char.current_version == v1 + 1
        old = reg.get_version(char.id, v1)
        new = reg.get_version(char.id, char.current_version)
        assert old is not None and new is not None
        assert "brave" not in (old.canonical_data.get("personality") or {}).get("traits", [])
        assert "brave" in (new.canonical_data.get("personality") or {}).get("traits", [])

        ctx = resolve_generation_context(
            session,
            SceneRequest(character_slug="ravi_test", character_version=v1),
        )
        assert ctx.character["version"] == v1
