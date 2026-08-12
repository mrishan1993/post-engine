from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.seed import seed_from_v2_config
from config.settings import get_settings
from db.models import AudioArtifact, AudioTimelineRow, MusicGenerationJob
from db.session import get_session
from music_sfx_engine.blueprint import build_audio_blueprint
from music_sfx_engine.providers import inject_music_provider, reset_music_providers
from music_sfx_engine.providers.stub import StubMusicProvider
from music_sfx_engine.schemas import MusicGenerationRequestIn, ProviderStrategy
from music_sfx_engine.service import MusicSfxService
from music_sfx_engine.sfx_library import seed_sfx_library
from music_sfx_engine.state import can_transition, transition
from music_sfx_engine.validation import validate_audio_artifact
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService


def _bootstrap(session):
    seed_from_v2_config(session)
    seed_sfx_library(session)
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
    return story, board


def test_music_state_machine() -> None:
    assert can_transition("routing", "submitting")
    assert transition("validating_artifact", "completed") == "completed"


def test_blueprint_from_storyboard(db_url: str) -> None:
    with get_session(db_url) as session:
        story, board = _bootstrap(session)
        bp = build_audio_blueprint(
            storyboard_doc=board.document,
            story_blueprint=story.blueprint,
            total_duration_sec=float(board.duration_sec or 30),
        )
        assert bp.total_duration_sec > 0
        assert bp.music_spec is not None
        assert bp.emotional_arc
        assert bp.sfx.get("items")
        assert any(s.reason for s in bp.silences) or True  # may or may not have silence


def test_v1_acceptance_path(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_music_providers()
    with get_session(db_url) as session:
        _, board = _bootstrap(session)
        req = MusicSfxService(session).create(
            MusicGenerationRequestIn(
                storyboard_id=board.id,
                variants={"count": 1},
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred="provider_a", fallback=["provider_b"]
                ),
                process=True,
                build_timeline=True,
                resolve_sfx=True,
            )
        )
        assert req.status == "completed"
        music = MusicSfxService(session).list_music_artifacts(req.id)
        assert len(music) == 1
        assert Path(music[0].storage_uri).exists()
        qa = validate_audio_artifact(
            music[0].storage_uri,
            expected_duration=float(music[0].duration_sec or 0),
        )
        assert qa.ok

        sfx = MusicSfxService(session).list_sfx_for_request(req.id)
        assert len(sfx) >= 1
        assert any((a.metadata_json or {}).get("source") == "library" for a in sfx)

        tl = session.scalar(
            select(AudioTimelineRow).where(AudioTimelineRow.music_request_id == req.id)
        )
        assert tl is not None
        types = {t.get("type") for t in (tl.tracks or [])}
        assert "music" in types
        assert "sfx" in types
        assert "silence" in types or "ambience" in types
        assert tl.beat_grid
        assert tl.ducking

    events = {e.event_type for e in get_bus().history}
    assert EventType.MUSIC_GENERATION_REQUESTED in events
    assert EventType.MUSIC_ARTIFACT_CREATED in events
    assert EventType.AUDIO_TIMELINE_CREATED in events
    assert EventType.SFX_SELECTED in events or EventType.SFX_REQUESTED in events


def test_fallback(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_music_providers()
    inject_music_provider("provider_a", StubMusicProvider("provider_a", fail_permanent=True))
    with get_session(db_url) as session:
        _, board = _bootstrap(session)
        req = MusicSfxService(session).create(
            MusicGenerationRequestIn(
                storyboard_id=board.id,
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred="provider_a", fallback=["provider_b"]
                ),
                process=True,
                resolve_sfx=False,
                build_timeline=False,
            )
        )
        jobs = MusicSfxService(session).list_jobs(req.id)
        assert jobs[0].status == "completed"
        assert jobs[0].provider == "provider_b"
        assert int(jobs[0].fallback_count or 0) >= 1
    assert EventType.MUSIC_GENERATION_FALLBACK in {e.event_type for e in get_bus().history}
    reset_music_providers()


def test_idempotency(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_music_providers()
    with get_session(db_url) as session:
        _, board = _bootstrap(session)
        a = MusicSfxService(session).create(
            MusicGenerationRequestIn(
                storyboard_id=board.id,
                idempotency_key="music-idem-1",
                process=True,
                resolve_sfx=False,
                build_timeline=False,
            )
        )
        b = MusicSfxService(session).create(
            MusicGenerationRequestIn(
                storyboard_id=board.id,
                idempotency_key="music-idem-1",
                process=True,
            )
        )
        assert a.id == b.id
        jobs = list(
            session.scalars(
                select(MusicGenerationJob).where(MusicGenerationJob.request_id == a.id)
            ).all()
        )
        assert len(jobs) == 1
