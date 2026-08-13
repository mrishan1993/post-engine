from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from amp_platform.events import EventType, get_bus, reset_bus
from asset_engine.seed import seed_from_v2_config
from config.settings import get_settings
from db.models import PronunciationEntry, VoiceArtifact, VoiceGenerationJob, VoiceTimelineRow
from db.session import get_session
from story_engine.schemas import StoryRequest
from story_engine.service import StoryService
from storyboard_engine.schemas import StoryboardRequest
from storyboard_engine.service import StoryboardService
from voice_generation_engine.providers import inject_voice_provider, reset_voice_providers
from voice_generation_engine.providers.stub import StubVoiceProvider
from voice_generation_engine.schemas import (
    DialogueLine,
    DialogueScript,
    ProviderStrategy,
    VoiceGenerationRequestIn,
)
from voice_generation_engine.service import VoiceGenerationService
from voice_generation_engine.spec_builder import build_voice_spec_from_text
from voice_generation_engine.state import can_transition, transition
from voice_generation_engine.validation import script_hash, validate_voice_artifact
from uuid import uuid4


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
    return story, board


def test_voice_state_machine() -> None:
    assert can_transition("routing", "submitting")
    assert transition("validating_artifact", "completed") == "completed"


def test_v1_acceptance_path(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_voice_providers()
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        info = VoiceGenerationService(session).get_character_voice("ghost_kid")
        assert info["voice_profile_id"]

        req = VoiceGenerationService(session).create(
            VoiceGenerationRequestIn(
                character_slug="ghost_kid",
                voice_spec=build_voice_spec_from_text(
                    text="Wait... did you hear that?",
                    character_slug="ghost_kid",
                    voice_profile_id=info["voice_profile_id"],
                    emotion="fear",
                    intensity=0.75,
                ),
                variants={"count": 2, "strategy": "different_emotion"},
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred="provider_a", fallback=["provider_b"]
                ),
                process=True,
                build_timeline=True,
            )
        )
        assert req.status == "completed"
        arts = VoiceGenerationService(session).list_artifacts(req.id)
        assert len(arts) == 2
        for a in arts:
            assert a.sha256
            assert a.script_hash == script_hash("Wait... did you hear that?")
            assert a.voice_profile_id == info["voice_profile_id"]
            assert Path(a.storage_uri).exists()
            assert a.timestamps and a.timestamps.get("words")
            qa = validate_voice_artifact(
                a.storage_uri, expected_duration=float(a.duration_sec or 0)
            )
            assert qa.ok
            assert qa.timestamps_available

        tl = session.scalar(select(VoiceTimelineRow).order_by(VoiceTimelineRow.created_at.desc()))
        assert tl is not None
        assert tl.segments

    events = {e.event_type for e in get_bus().history}
    assert EventType.VOICE_GENERATION_REQUESTED in events
    assert EventType.VOICE_ARTIFACT_CREATED in events
    assert EventType.VOICE_TECHNICAL_QA_COMPLETED in events
    assert EventType.VOICE_TIMELINE_CREATED in events


def test_multi_character_dialogue_timeline(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_voice_providers()
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        VoiceGenerationService(session).create(
            VoiceGenerationRequestIn(
                dialogue=DialogueScript(
                    lines=[
                        DialogueLine(
                            speaker="ghost_kid",
                            line="What was that?",
                            emotion="confused",
                            intensity=0.4,
                        ),
                        DialogueLine(
                            speaker="ghost_kid",
                            line="Don't open that door.",
                            emotion="fear",
                            intensity=0.85,
                        ),
                    ]
                ),
                variants={"count": 1},
                provider_strategy=ProviderStrategy(mode="preferred", preferred="provider_a"),
                process=True,
                build_timeline=True,
            )
        )
        tls = list(session.scalars(select(VoiceTimelineRow)).all())
        assert tls
        assert len(tls[-1].segments or []) == 2
        assert float(tls[-1].duration_sec) > 0


def test_fallback_maps_voice(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_bus()
    reset_voice_providers()
    inject_voice_provider("provider_a", StubVoiceProvider("provider_a", fail_permanent=True))
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        req = VoiceGenerationService(session).create(
            VoiceGenerationRequestIn(
                character_slug="ghost_kid",
                voice_spec=build_voice_spec_from_text(
                    text="Don't open that door.",
                    character_slug="ghost_kid",
                    emotion="fear",
                ),
                provider_strategy=ProviderStrategy(
                    mode="preferred", preferred="provider_a", fallback=["provider_b"]
                ),
                process=True,
                build_timeline=False,
            )
        )
        jobs = VoiceGenerationService(session).list_jobs(req.id)
        assert jobs[0].status == "completed"
        assert jobs[0].provider == "provider_b"
        assert jobs[0].provider_voice_id
        assert "provider_b" in (jobs[0].provider_voice_id or "")
        assert int(jobs[0].fallback_count or 0) >= 1
    assert EventType.VOICE_GENERATION_FALLBACK in {e.event_type for e in get_bus().history}
    reset_voice_providers()


def test_pronunciation_dictionary(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_voice_providers()
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        session.add(
            PronunciationEntry(
                id=str(uuid4()),
                term="Bangalore",
                language="en-IN",
                pronunciation="Bengaluru",
            )
        )
        session.flush()
        req = VoiceGenerationService(session).create(
            VoiceGenerationRequestIn(
                character_slug="ghost_kid",
                voice_spec=build_voice_spec_from_text(
                    text="Meet me in Bangalore tonight.",
                    character_slug="ghost_kid",
                    emotion="urgent",
                ),
                process=True,
                build_timeline=False,
            )
        )
        art = VoiceGenerationService(session).list_artifacts(req.id)[0]
        # script_hash is of original text; pronounced text is provider-facing
        assert art.script_hash == script_hash("Meet me in Bangalore tonight.")
        assert Path(art.storage_uri).read_text(encoding="utf-8", errors="ignore") or True
        meta = Path(art.storage_uri).with_suffix(".meta.json").read_text(encoding="utf-8")
        assert "Bengaluru" in meta


def test_idempotency(db_url: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_voice_providers()
    with get_session(db_url) as session:
        seed_from_v2_config(session)
        a = VoiceGenerationService(session).create(
            VoiceGenerationRequestIn(
                character_slug="ghost_kid",
                voice_spec=build_voice_spec_from_text(
                    text="Hello.",
                    character_slug="ghost_kid",
                ),
                idempotency_key="voice-idem-1",
                process=True,
                build_timeline=False,
            )
        )
        b = VoiceGenerationService(session).create(
            VoiceGenerationRequestIn(
                character_slug="ghost_kid",
                voice_spec=build_voice_spec_from_text(
                    text="Hello.",
                    character_slug="ghost_kid",
                ),
                idempotency_key="voice-idem-1",
                process=True,
            )
        )
        assert a.id == b.id
        jobs = list(
            session.scalars(
                select(VoiceGenerationJob).where(VoiceGenerationJob.request_id == a.id)
            ).all()
        )
        assert len(jobs) == 1
