from __future__ import annotations

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.seed import seed_from_v2_config
from db.models import PromptPackage, PromptSpec
from db.session import get_session
from prompt_engine.compiler import compile_package, shot_to_cgs
from prompt_engine.critic import detect_conflicts, enrich_package
from prompt_engine.registry import rank_providers, select_provider
from prompt_engine.schemas import CanonicalGenerationSpec, CompileRequest, PromptPackageDoc
from prompt_engine.service import PromptService
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService


def test_shot_to_cgs_and_veo_compile() -> None:
    shot = {
        "id": "shot_test",
        "duration_sec": 4,
        "shot_type": "medium",
        "action": "Ravi walks slowly toward Door 13",
        "subject": {"name": "Ravi", "character_id": None},
        "expression": {"emotion": "terrified"},
        "camera": {"angle": "eye_level", "movement": "slow_push"},
        "environment": {"location_name": "Haunted School", "state": "flickering"},
        "composition": {"framing": "center"},
        "lighting": {"style": "low_key", "intensity": "low"},
        "generation": {"reference_assets": []},
        "audio": {"music": {"intensity": 0.4}},
    }
    spec = shot_to_cgs(
        shot,
        scene={"objective": "Create dread", "narrative_function": "conflict", "id": "sc1"},
        global_direction={"aspect_ratio": "9:16", "visual_style": "cinematic_horror"},
        character_context={"name": "Ravi", "canonical_data": {"identity": {"age": 12}}},
    )
    assert isinstance(spec, CanonicalGenerationSpec)
    assert spec.modality == "video"
    assert spec.constraints["preserve_character_identity"] is True

    provider, package = compile_package(spec, provider="veo")
    assert provider == "veo"
    assert "Ravi" in package.positive_prompt
    assert "slow push" in package.positive_prompt.lower() or "slow_push" in package.positive_prompt
    package = enrich_package(spec, package, provider="veo")
    assert package.quality is not None
    assert package.quality.overall >= 0.5
    assert package.validation is not None


def test_conflict_detection_motion() -> None:
    spec = CanonicalGenerationSpec(
        modality="video",
        objective="walk",
        subject={"action": "walks slowly toward the door", "name": "Ravi"},
        camera={"movement": "static", "shot_type": "medium"},
    )
    pkg = PromptPackageDoc(
        provider="veo",
        model="x",
        modality="video",
        positive_prompt="Ravi sprinting fast through the hallway at full speed",
    )
    conflicts = detect_conflicts(spec, pkg)
    assert any(c.type == "motion_conflict" for c in conflicts)


def test_provider_ranking_prefers_character_consistency() -> None:
    ranked = rank_providers(
        "video",
        needs={"preserve_character_identity": True, "duration_sec": 4},
    )
    assert ranked[0][0] == "veo"
    assert select_provider("music") == "suno"


def test_compile_from_storyboard_persists_and_emits(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        story = StoryService(session).generate(
            StoryRequest.model_validate(
                {
                    "content_opportunity": {
                        "topic": "POV horror",
                        "emotion": "fear",
                        "platform": "instagram_reels",
                    },
                    "creative_direction": {
                        "format": "POV",
                        "target_duration_sec": 30,
                        "visual_style": "cinematic_horror",
                    },
                    "characters": [{"character_slug": "ghost_kid", "role": "protagonist"}],
                    "candidate_count": 1,
                    "story_type": "pov_horror",
                }
            )
        )[0]
        board = StoryboardService(session).generate(
            StoryboardRequest(
                story_id=story.id,
                character_slugs=["ghost_kid"],
                location_query="Haunted School",
            )
        )
        packages = PromptService(session).compile(
            CompileRequest(
                storyboard_id=board.id,
                provider="veo",
                compile_all_shots=False,
            )
        )
        assert len(packages) == 1
        assert packages[0].provider == "veo"
        assert packages[0].prompt_spec_id
        spec = session.get(PromptSpec, packages[0].prompt_spec_id)
        assert spec is not None
        assert spec.canonical_spec["modality"] == "video"
        assert session.get(PromptPackage, packages[0].id) is not None

    assert EventType.PROMPT_PACK_CREATED in {e.event_type for e in get_bus().history}


def test_experiment_creates_variants(db_url: str) -> None:
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        story = StoryService(session).generate(
            StoryRequest.model_validate(
                {
                    "content_opportunity": {
                        "topic": "POV horror",
                        "emotion": "fear",
                        "platform": "instagram_reels",
                    },
                    "creative_direction": {"format": "POV", "target_duration_sec": 30},
                    "characters": [{"character_slug": "ghost_kid", "role": "protagonist"}],
                    "candidate_count": 1,
                }
            )
        )[0]
        board = StoryboardService(session).generate(
            StoryboardRequest(story_id=story.id, character_slugs=["ghost_kid"])
        )
        packages = PromptService(session).compile(
            CompileRequest(storyboard_id=board.id, experiment=True, modality="video")
        )
        assert len(packages) >= 2
        providers = {p.provider for p in packages}
        assert "veo" in providers or "runway" in providers
