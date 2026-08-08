from __future__ import annotations

from amp_platform.events import EventType, get_bus, reset_bus
from amp_platform.events.types import PredictionCreated
from db.session import get_session
from trend_engine.v2.pipeline import run_v2_intelligence


def test_event_envelope_roundtrip() -> None:
    reset_bus()
    bus = get_bus()
    seen: list[str] = []
    bus.subscribe(EventType.PREDICTION_CREATED, lambda e: seen.append(e.event_type))
    bus.publish(
        EventType.PREDICTION_CREATED,
        PredictionCreated(
            prediction_id=1,
            virality_probability=0.8,
            expected_views=1000,
            confidence=0.7,
            final_opportunity_score=70,
            model_version="rule_v1",
        ),
        producer="test",
    )
    assert seen == [EventType.PREDICTION_CREATED]
    assert bus.history[0].producer == "test"
    assert bus.history[0].payload["prediction_id"] == 1


def test_v2_emits_amp_events(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        run_v2_intelligence(session, vertical="horror_narration")
    types = {e.event_type for e in get_bus().history}
    assert EventType.TREND_OPPORTUNITY_CREATED in types
    assert EventType.CONTENT_BRIEF_CREATED in types
    assert EventType.PREDICTION_CREATED in types
