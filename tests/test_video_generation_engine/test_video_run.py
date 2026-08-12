from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.seed import seed_from_v2_config
from config.settings import get_settings
from db.models import VideoArtifact, VideoGenerationJob
from db.session import get_session
from prompt_engine.schemas import CompileRequest
from prompt_engine.service import PromptService
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService
from video_generation_engine.duration import resolve_duration
from video_generation_engine.providers import inject_video_provider, reset_video_providers
from video_generation_engine.providers.stub import StubVideoProvider
from video_generation_engine.schemas import ProviderStrategy, VideoGenerationRequestIn
from video_generation_engine.service import VideoGenerationService
from video_generation_engine.state import can_transition, transition
from video_generation_engine.validation import validate_video_artifact


def _bootstrap(session):
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
        CompileRequest(storyboard_id=board.id, provider="veo", compile_all_shots=False)
    )
    return board, packages[0]


def test_video_state_machine() -> None:
    assert can_transition("routing", "preparing_references")
    assert transition("validating_artifact", "completed") == "completed"


def test_duration_strategy_explicit() -> None:
    info = resolve_duration(5.5, "provider_a", strategy="nearest")
    assert info["changed"] is True
    assert info["resolved"] in {2, 4, 5, 6, 8}
    assert info["reason"]


def test_v1_acceptance_path(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_video_providers()
    with get_session(db_url) as session:
        _, package = _bootstrap(session)
        req = VideoGenerationService(session).create(
            VideoGenerationRequestIn(
                prompt_package_id=package.id,
                variants={"count": 2, "strategy": "same_provider"},
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred="provider_a", fallback=["provider_b"]
                ),
                priority="high",
                process=True,
            )
        )
        assert req.status == "completed"
        arts = VideoGenerationService(session).list_artifacts(req.id)
        assert len(arts) == 2
        for a in arts:
            assert a.width == 1080
            assert a.height == 1920
            assert a.sha256
            assert Path(a.storage_uri).exists()
            qa = validate_video_artifact(
                a.storage_uri,
                expected_aspect="9:16",
                expected_resolution="1080x1920",
            )
            assert qa.ok
            assert (a.technical_qa or {}).get("ok") is True

    types = {e.event_type for e in get_bus().history}
    assert EventType.VIDEO_GENERATION_REQUESTED in types
    assert EventType.VIDEO_ARTIFACT_CREATED in types
    assert EventType.VIDEO_TECHNICAL_QA_COMPLETED in types


def test_fallback_recompiles(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_video_providers()
    inject_video_provider("provider_a", StubVideoProvider("provider_a", fail_permanent=True))
    with get_session(db_url) as session:
        _, package = _bootstrap(session)
        req = VideoGenerationService(session).create(
            VideoGenerationRequestIn(
                prompt_package_id=package.id,
                provider_strategy=ProviderStrategy(
                    mode="preferred",
                    preferred="provider_a",
                    fallback=["provider_b"],
                ),
                process=True,
            )
        )
        jobs = VideoGenerationService(session).list_jobs(req.id)
        assert jobs[0].status == "completed"
        assert jobs[0].provider == "provider_b"
        assert int(jobs[0].fallback_count or 0) >= 1
        arts = list(
            session.scalars(
                select(VideoArtifact).where(VideoArtifact.generation_job_id == jobs[0].id)
            ).all()
        )
        assert arts[0].provider == "provider_b"
    assert EventType.VIDEO_GENERATION_FALLBACK in {e.event_type for e in get_bus().history}
    reset_video_providers()


def test_idempotency(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_video_providers()
    with get_session(db_url) as session:
        _, package = _bootstrap(session)
        a = VideoGenerationService(session).create(
            VideoGenerationRequestIn(
                prompt_package_id=package.id,
                idempotency_key="video-idem-1",
                process=True,
            )
        )
        b = VideoGenerationService(session).create(
            VideoGenerationRequestIn(
                prompt_package_id=package.id,
                idempotency_key="video-idem-1",
                process=True,
            )
        )
        assert a.id == b.id
        assert session.scalar(select(VideoGenerationJob).where(VideoGenerationJob.request_id == a.id))
