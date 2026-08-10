from __future__ import annotations

from sqlalchemy import func, select

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.characters import CharacterRegistry
from asset_engine.schemas import CanonRules, CharacterCanonical
from db.models import NarrativePattern, Story, StoryVersion
from db.session import get_session
from story_engine.critic import critique_blueprint, evaluate_quality
from story_engine.generator import build_blueprint
from story_engine.patterns import ensure_default_patterns
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService


def _horror_request(**overrides: object) -> StoryRequest:
    data: dict = {
        "content_opportunity": {
            "topic": "POV horror",
            "trend_score": 91,
            "trend_stage": "growing",
            "emotion": "fear",
            "platform": "instagram_reels",
        },
        "creative_direction": {
            "format": "POV",
            "visual_style": "cinematic_horror",
            "pacing": "fast",
            "target_duration_sec": 30,
        },
        "prediction": {"virality_probability": 0.84, "predicted_retention": 0.71},
        "story_type": "pov_horror",
        "candidate_count": 3,
        "max_revisions": 2,
    }
    data.update(overrides)
    return StoryRequest.model_validate(data)


def test_blueprint_fits_duration_and_has_hook() -> None:
    req = _horror_request()
    bp = build_blueprint(req, character_context={"name": "Ravi", "traits": ["curious"]})
    assert bp.hook.hook_text
    assert bp.duration.target_seconds == 30
    assert abs(bp.duration.estimated_seconds - 30) <= 1.5
    assert bp.open_loops
    assert bp.tension_curve
    quality = evaluate_quality(bp, req)
    assert 0.5 <= quality.overall <= 1.0
    critic = critique_blueprint(bp, req)
    assert critic.critic_score >= 0.0


def test_generate_candidates_persist_and_emit_events(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        CharacterRegistry(session).create(
            slug="ghost_kid",
            name="Ghost Kid",
            canonical=CharacterCanonical(
                identity={"age": 12},
                personality={"traits": ["curious", "nonviolent"]},
                canon=CanonRules(forbidden=["guns", "gore"]),
            ),
            status="active",
        )
        req = _horror_request(
            characters=[{"character_slug": "ghost_kid", "role": "protagonist"}]
        )
        stories = StoryService(session).generate(req)
        assert len(stories) == 3
        assert all(isinstance(s, Story) for s in stories)
        assert stories[0].quality_score is not None
        assert stories[0].blueprint["hook"]["hook_text"]
        versions = list(
            session.scalars(
                select(StoryVersion).where(StoryVersion.story_id == stories[0].id)
            ).all()
        )
        assert len(versions) == 1
        patterns = list(session.scalars(select(NarrativePattern)).all())
        assert len(patterns) >= 1
        assert stories[0].character_ids

    types = {e.event_type for e in get_bus().history}
    assert EventType.STORY_CREATED in types


def test_select_winner_and_approve(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        ensure_default_patterns(session)
        stories = StoryService(session).generate(_horror_request(candidate_count=2))
        winner = StoryService(session).select_winner(stories)
        assert winner.status == "approved"
        losers = [s for s in stories if s.id != winner.id]
        assert all(s.status == "rejected" for s in losers)

    assert EventType.STORY_CREATED in {e.event_type for e in get_bus().history}


def test_revise_bumps_version(db_url: str) -> None:
    with get_session(db_url) as session:
        stories = StoryService(session).generate(_horror_request(candidate_count=1))
        story = StoryService(session).revise(stories[0].id)
        assert story.current_version == 2
        count = session.scalar(
            select(func.count()).select_from(StoryVersion).where(StoryVersion.story_id == story.id)
        )
        assert count == 2
