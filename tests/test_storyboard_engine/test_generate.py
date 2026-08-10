from __future__ import annotations

from sqlalchemy import select

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.characters import CharacterRegistry
from asset_engine.schemas import CharacterCanonical
from asset_engine.seed import seed_from_v2_config
from db.models import Storyboard, StoryboardScene, StoryboardShot
from db.session import get_session
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.critic import critique_storyboard, evaluate_quality
from storyboard_engine.generator import build_storyboard
from storyboard_engine.schemas import StoryboardDocument, StoryboardRequest
from storyboard_engine.service import StoryboardService


def _make_story(session, *, character_slug: str | None = "ghost_kid"):
    return StoryService(session).generate(
        StoryRequest.model_validate(
            {
                "content_opportunity": {
                    "topic": "POV horror",
                    "emotion": "fear",
                    "platform": "instagram_reels",
                    "trend_score": 90,
                },
                "creative_direction": {
                    "format": "POV",
                    "target_duration_sec": 30,
                    "visual_style": "cinematic_horror",
                    "pacing": "fast",
                },
                "characters": (
                    [{"character_slug": character_slug, "role": "protagonist"}]
                    if character_slug
                    else []
                ),
                "prediction": {"virality_probability": 0.84, "predicted_retention": 0.55},
                "candidate_count": 1,
                "story_type": "pov_horror",
            }
        )
    )[0]


def test_build_storyboard_from_blueprint_timing() -> None:
    from story_engine.generator import build_blueprint

    bp = build_blueprint(
        StoryRequest.model_validate(
            {
                "content_opportunity": {
                    "topic": "POV horror",
                    "emotion": "fear",
                    "platform": "instagram_reels",
                },
                "creative_direction": {"format": "POV", "target_duration_sec": 30},
            }
        ),
        character_context={"name": "Ravi", "traits": ["curious"]},
    )
    doc = build_storyboard(
        bp,
        StoryboardRequest(platform="instagram_reels", predicted_retention=0.55),
        character_context={"name": "Ravi"},
    )
    assert isinstance(doc, StoryboardDocument)
    assert doc.scenes
    assert doc.scenes[0].narrative_function == "hook"
    assert doc.scenes[0].start_time_sec == 0
    assert abs(doc.duration_sec - 30) <= 2.5
    assert all(sc.shots for sc in doc.scenes)
    assert doc.pattern_interrupts
    assert doc.pacing.average_shot_duration_sec > 0
    # No provider syntax
    blob = str(doc.model_dump())
    assert "veo" not in blob.lower()
    assert "runway" not in blob.lower()
    assert "elevenlabs" not in blob.lower()

    quality = evaluate_quality(doc, StoryboardRequest(platform="instagram_reels"))
    critic = critique_storyboard(doc, StoryboardRequest(platform="instagram_reels"))
    assert quality.overall >= 0.6
    assert critic.hook_visual_interest


def test_generate_persists_scenes_shots_and_events(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        story = _make_story(session)
        board = StoryboardService(session).generate(
            StoryboardRequest(
                story_id=story.id,
                platform="instagram_reels",
                character_slugs=["ghost_kid"],
                location_query="Haunted School",
            )
        )
        assert board.version == 1
        assert board.quality_score is not None
        scenes = list(
            session.scalars(
                select(StoryboardScene).where(StoryboardScene.storyboard_id == board.id)
            ).all()
        )
        assert len(scenes) >= 5
        shots = list(
            session.scalars(
                select(StoryboardShot).where(
                    StoryboardShot.scene_id.in_([s.id for s in scenes])
                )
            ).all()
        )
        assert len(shots) >= len(scenes)
        assert board.document["global_direction"]["aspect_ratio"] == "9:16"
        assert board.document["asset_requirements"]

    types = {e.event_type for e in get_bus().history}
    assert EventType.STORYBOARD_CREATED in types


def test_revise_creates_new_version(db_url: str) -> None:
    with get_session(db_url) as session:
        CharacterRegistry(session).create(
            slug="ravi_sb",
            name="Ravi",
            canonical=CharacterCanonical(
                identity={"age": 12},
                personality={"traits": ["curious"]},
            ),
            status="active",
        )
        story = _make_story(session, character_slug="ravi_sb")
        board = StoryboardService(session).generate(
            StoryboardRequest(story_id=story.id, character_slugs=["ravi_sb"])
        )
        revised = StoryboardService(session).revise(board.id)
        assert revised.id != board.id
        assert revised.version == board.version + 1
        assert revised.story_id == board.story_id


def test_approve_emits_event(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        story = _make_story(session, character_slug=None)
        board = StoryboardService(session).generate(StoryboardRequest(story_id=story.id))
        approved = StoryboardService(session).approve(board.id)
        assert approved.status == "approved"
        assert session.get(Storyboard, board.id).status == "approved"
    assert EventType.STORYBOARD_APPROVED in {e.event_type for e in get_bus().history}
