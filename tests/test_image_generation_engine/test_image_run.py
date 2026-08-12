from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.seed import seed_from_v2_config
from config.settings import get_settings
from db.models import ImageArtifact, ImageGenerationJob
from db.session import get_session
from image_generation_engine.providers import inject_image_provider, reset_image_providers
from image_generation_engine.providers.stub import StubImageProvider
from image_generation_engine.references import rank_and_trim_references
from image_generation_engine.schemas import (
    ImageEditRequestIn,
    ImageGenerationRequestIn,
    ImageReference,
    ProviderStrategy,
)
from image_generation_engine.service import ImageGenerationService
from image_generation_engine.state import can_transition, transition
from image_generation_engine.validation import validate_image_artifact
from prompt_engine.schemas import CompileRequest
from prompt_engine.service import PromptService
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService


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
        CompileRequest(
            storyboard_id=board.id,
            modality="image",
            provider="gpt_image",
            compile_all_shots=False,
        )
    )
    return board, packages[0]


def test_image_state_machine() -> None:
    assert can_transition("routing", "preparing_references")
    assert transition("validating_artifact", "completed") == "completed"


def test_reference_ranking() -> None:
    refs = [
        ImageReference(asset_id="env", role="environment", score=0.64),
        ImageReference(asset_id="face", role="face", score=0.98),
        ImageReference(asset_id="pose", role="pose", score=0.77),
        ImageReference(asset_id="style", role="style", score=0.71),
    ]
    trimmed = rank_and_trim_references(refs, max_references=2)
    assert [r.asset_id for r in trimmed] == ["face", "pose"]


def test_v1_acceptance_path(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_image_providers()
    with get_session(db_url) as session:
        _, package = _bootstrap(session)
        req = ImageGenerationService(session).create(
            ImageGenerationRequestIn(
                prompt_package_id=package.id,
                purpose="storyboard_keyframe",
                variants={"count": 2, "strategy": "different_composition"},
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred="provider_a", fallback=["provider_b"]
                ),
                priority="high",
                process=True,
            )
        )
        assert req.status == "completed"
        arts = ImageGenerationService(session).list_artifacts(req.id)
        assert len(arts) == 2
        for a in arts:
            assert a.width == 1024
            assert a.height == 1536
            assert a.sha256
            assert a.phash
            assert Path(a.storage_uri).exists()
            qa = validate_image_artifact(
                a.storage_uri,
                expected_aspect="9:16",
                expected_resolution="1024x1536",
            )
            assert qa.ok
            assert (a.technical_qa or {}).get("ok") is True
            assert float((a.technical_qa or {}).get("technical_score") or 0) >= 0.85

    types = {e.event_type for e in get_bus().history}
    assert EventType.IMAGE_GENERATION_REQUESTED in types
    assert EventType.IMAGE_ARTIFACT_CREATED in types
    assert EventType.IMAGE_TECHNICAL_QA_COMPLETED in types


def test_fallback_recompiles(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_image_providers()
    inject_image_provider("provider_a", StubImageProvider("provider_a", fail_permanent=True))
    with get_session(db_url) as session:
        _, package = _bootstrap(session)
        req = ImageGenerationService(session).create(
            ImageGenerationRequestIn(
                prompt_package_id=package.id,
                provider_strategy=ProviderStrategy(
                    mode="preferred",
                    preferred="provider_a",
                    fallback=["provider_b"],
                ),
                process=True,
            )
        )
        jobs = ImageGenerationService(session).list_jobs(req.id)
        assert jobs[0].status == "completed"
        assert jobs[0].provider == "provider_b"
        assert int(jobs[0].fallback_count or 0) >= 1
        arts = list(
            session.scalars(
                select(ImageArtifact).where(ImageArtifact.generation_job_id == jobs[0].id)
            ).all()
        )
        assert arts[0].provider == "provider_b"
    assert EventType.IMAGE_GENERATION_FALLBACK in {e.event_type for e in get_bus().history}
    reset_image_providers()


def test_edit_creates_versioned_artifact(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_image_providers()
    with get_session(db_url) as session:
        _, package = _bootstrap(session)
        req = ImageGenerationService(session).create(
            ImageGenerationRequestIn(
                prompt_package_id=package.id,
                variants={"count": 1},
                provider_strategy=ProviderStrategy(mode="preferred", preferred="provider_a"),
                process=True,
            )
        )
        parent = ImageGenerationService(session).list_artifacts(req.id)[0]
        edit_req = ImageGenerationService(session).edit(
            ImageEditRequestIn(
                artifact_id=parent.id,
                instruction="change expression to fear, keep identity",
                process=True,
            )
        )
        assert edit_req.status == "completed"
        edited = ImageGenerationService(session).list_artifacts(edit_req.id)[0]
        assert edited.parent_artifact_id == parent.id
        assert edited.id != parent.id
        assert Path(edited.storage_uri).exists()
        # Original unchanged
        still = session.get(ImageArtifact, parent.id)
        assert still is not None
        assert still.storage_uri == parent.storage_uri

    types = {e.event_type for e in get_bus().history}
    assert EventType.IMAGE_EDITED in types
    assert EventType.IMAGE_VERSION_CREATED in types


def test_idempotency(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_image_providers()
    with get_session(db_url) as session:
        _, package = _bootstrap(session)
        a = ImageGenerationService(session).create(
            ImageGenerationRequestIn(
                prompt_package_id=package.id,
                idempotency_key="img-idem-1",
                process=True,
            )
        )
        b = ImageGenerationService(session).create(
            ImageGenerationRequestIn(
                prompt_package_id=package.id,
                idempotency_key="img-idem-1",
                process=True,
            )
        )
        assert a.id == b.id
        jobs = list(session.scalars(select(ImageGenerationJob)).all())
        assert len([j for j in jobs if j.request_id == a.id]) == 1
