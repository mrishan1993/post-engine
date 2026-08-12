from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.seed import seed_from_v2_config
from config.settings import get_settings
from db.models import MediaArtifact
from db.session import get_session
from generation_engine.providers.registry import inject_provider, reset_providers
from generation_engine.providers.stub import StubGenerationProvider
from generation_engine.schemas import GenerationRequestIn, ProviderStrategy, VariantsConfig
from generation_engine.service import GenerationService
from generation_engine.state import can_transition, transition
from prompt_engine.schemas import CompileRequest
from prompt_engine.service import PromptService
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService


def _bootstrap_package(session):
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


def test_state_machine_allows_happy_path() -> None:
    assert can_transition("queued", "validating")
    assert transition("completed", "qa_pending") == "qa_pending"
    try:
        transition("approved", "queued")
        assert False, "should raise"
    except ValueError:
        pass


def test_generate_creates_artifact_and_events(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_providers()
    with get_session(db_url) as session:
        _, package = _bootstrap_package(session)
        req = GenerationService(session).create(
            GenerationRequestIn(
                prompt_package_id=package.id,
                modality="video",
                variants=VariantsConfig(count=2, strategy="same_provider_seed"),
                provider_strategy=ProviderStrategy(mode="preferred", preferred="veo"),
                process=True,
            )
        )
        assert req.status == "completed"
        jobs = GenerationService(session).list_jobs(req.id)
        assert len(jobs) == 2
        assert all(j.status == "approved" for j in jobs)
        arts = GenerationService(session).list_artifacts(req.id)
        assert len(arts) == 2
        for a in arts:
            assert a.sha256
            assert Path(a.storage_uri).exists()
            assert (a.technical_qa or {}).get("ok") is True

    types = {e.event_type for e in get_bus().history}
    assert EventType.GENERATION_REQUESTED in types
    assert EventType.GENERATION_COMPLETED in types
    assert EventType.ARTIFACT_CREATED in types


def test_idempotency(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_providers()
    with get_session(db_url) as session:
        _, package = _bootstrap_package(session)
        a = GenerationService(session).create(
            GenerationRequestIn(
                prompt_package_id=package.id,
                idempotency_key="idem-1",
                process=True,
            )
        )
        b = GenerationService(session).create(
            GenerationRequestIn(
                prompt_package_id=package.id,
                idempotency_key="idem-1",
                process=True,
            )
        )
        assert a.id == b.id


def test_fallback_on_permanent_primary_failure(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_providers()
    inject_provider("veo", StubGenerationProvider("veo", fail_permanent=True))
    with get_session(db_url) as session:
        _, package = _bootstrap_package(session)
        req = GenerationService(session).create(
            GenerationRequestIn(
                prompt_package_id=package.id,
                modality="video",
                provider_strategy=ProviderStrategy(
                    mode="preferred",
                    preferred="veo",
                    fallback=["runway"],
                    max_provider_switches=2,
                ),
                process=True,
            )
        )
        jobs = GenerationService(session).list_jobs(req.id)
        assert len(jobs) == 1
        job = jobs[0]
        assert job.status == "approved"
        assert job.provider == "runway"
        assert int(job.fallback_count or 0) >= 1
        arts = list(
            session.scalars(
                select(MediaArtifact).where(MediaArtifact.generation_job_id == job.id)
            ).all()
        )
        assert len(arts) == 1
        assert arts[0].provider == "runway"

    assert EventType.GENERATION_FALLBACK in {e.event_type for e in get_bus().history}
    reset_providers()


def test_budget_blocks_expensive_job(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_providers()
    with get_session(db_url) as session:
        _, package = _bootstrap_package(session)
        req = GenerationService(session).create(
            GenerationRequestIn(
                prompt_package_id=package.id,
                budget={"max_cost": 0.0001, "currency": "USD"},
                process=True,
            )
        )
        jobs = GenerationService(session).list_jobs(req.id)
        assert jobs[0].status == "failed_permanently"
