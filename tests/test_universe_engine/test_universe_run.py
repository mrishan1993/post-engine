from __future__ import annotations

from amp_platform.events import EventType, get_bus, reset_bus
from db.session import get_session
from universe_engine.continuity import detect_first_meet_claim
from universe_engine.schemas import (
    AddCanonFactRequest,
    AssembleContextRequest,
    CreateCharacterRequest,
    CreateUniverseRequest,
    EvolveCharacterRequest,
    RecordEventRequest,
    UpdatePerceptionRequest,
    UpsertRelationshipRequest,
    ValidateContinuityRequest,
)
from universe_engine.service import UniverseService


def test_first_meet_detector() -> None:
    assert detect_first_meet_claim("Alex meets B for the first time")
    assert not detect_first_meet_claim("Alex meets B again after their argument")


def test_universe_end_to_end(db_url: str) -> None:
    reset_bus()
    bus = get_bus()
    with get_session(db_url) as session:
        svc = UniverseService(session)
        universe = svc.create_universe(
            CreateUniverseRequest(name="Hotel Stories", slug="hotel_stories_test")
        )
        assert universe.version == 1

        alex = svc.create_character(
            CreateCharacterRequest(
                universe_id=universe.universe_id,
                slug="alex",
                name="Alex",
                identity={"occupation": "hotel_employee", "location": "Delhi"},
                personality={"traits": ["introverted", "funny", "anxious"]},
                personality_scores={"confidence": 0.3, "humor": 0.82, "curiosity": 0.74},
                goals=["Become a manager"],
                fears=["Public embarrassment"],
                behavioral_rules=[
                    "Avoids confrontation.",
                    "Uses humor under stress.",
                    "Never lies about family.",
                ],
            )
        )
        bee = svc.create_character(
            CreateCharacterRequest(
                universe_id=universe.universe_id,
                slug="character_b",
                name="B",
                personality_scores={"confidence": 0.8},
            )
        )
        assert alex.behavioral_rules
        assert alex.current_state.get("personality_scores", {}).get("confidence") == 0.3

        # AC3/AC5 — event + memory
        ev = svc.record_event(
            RecordEventRequest(
                universe_id=universe.universe_id,
                description="Alex accidentally embarrasses himself in front of a guest.",
                participants=[alex.character_id],
                episode_key="ep1",
                emotional_impact=0.9,
                consequences=["Anxiety +10"],
                canon_status="canon",
            )
        )
        assert ev["memories"]
        assert ev["event_id"]

        # AC4 — relationship evolution
        svc.upsert_relationship(
            UpsertRelationshipRequest(
                universe_id=universe.universe_id,
                source_id=alex.character_id,
                target_id=bee.character_id,
                relationship_type="stranger",
                strength=0.1,
            )
        )
        rel = svc.upsert_relationship(
            UpsertRelationshipRequest(
                universe_id=universe.universe_id,
                source_id=alex.character_id,
                target_id=bee.character_id,
                relationship_type="friend",
                strength=0.7,
                traits={"trust": 0.6},
            )
        )
        assert rel["type"] == "friend"
        assert len(rel["history"]) >= 2

        svc.record_event(
            RecordEventRequest(
                universe_id=universe.universe_id,
                description="Alex and B share a difficult shift together.",
                participants=[alex.character_id, bee.character_id],
                episode_key="ep20",
                emotional_impact=0.6,
                canon_status="canon",
            )
        )

        # AC6/AC15 — canon with lineage
        fact = svc.add_canon_fact(
            AddCanonFactRequest(
                universe_id=universe.universe_id,
                subject="alex",
                predicate="works_as",
                object="hotel_employee",
                source="Episode 12",
                authority="human",
            )
        )
        assert fact["status"] == "canon"
        assert fact["source"] == "Episode 12"

        # AC7 — canon conflict detection (no silent overwrite)
        conflicted = svc.add_canon_fact(
            AddCanonFactRequest(
                universe_id=universe.universe_id,
                subject="alex",
                predicate="works_as",
                object="astronaut",
                source="bad_draft",
            )
        )
        assert conflicted["conflict_id"]
        assert conflicted["status"] == "provisional"

        # AC10 — character evolution
        evolved = svc.evolve_character(
            EvolveCharacterRequest(
                character_id=alex.character_id,
                personality_delta={"confidence": 0.12},
                development_stage="growth",
                reason="arc progress",
                approved_by="human",
            )
        )
        assert evolved.current_state["personality_scores"]["confidence"] == 0.42
        assert evolved.version >= 2

        # AC11 — audience perception separate from canon
        perc = svc.update_perception(
            UpdatePerceptionRequest(
                character_id=alex.character_id,
                universe_id=universe.universe_id,
                perceived_traits={"secretly_confident": True},
                affinity=91,
                requests=["Give Alex and B a series"],
            )
        )
        assert perc["note"] == "perception is not canon"

        # AC8 — relevant context retrieval
        ctx = svc.assemble_context(
            AssembleContextRequest(
                universe_id=universe.universe_id,
                character_slugs=["alex", "character_b"],
                premise="Alex and B hotel adventure",
                memory_limit=5,
            )
        )
        assert ctx.character_context
        assert ctx.memories
        assert ctx.relationship_context
        assert ctx.canon_constraints
        assert ctx.audience_context.get("alex")
        assert ctx.visual_context.get("alex")
        assert ctx.voice_context.get("alex")

        # AC9 — continuity validation
        report = svc.validate_continuity(
            ValidateContinuityRequest(
                universe_id=universe.universe_id,
                premise="Alex meets Character B for the first time.",
                character_slugs=["alex", "character_b"],
                behavioral_actions=["Alex immediately starts a physical confrontation."],
                proposed_facts=[
                    {"subject": "alex", "predicate": "works_as", "object": "pilot"}
                ],
            )
        )
        assert report.result in {"CONTINUITY_WARNING", "CONTINUITY_FAIL"}
        assert report.warnings or report.failures
        assert report.conflict_ids

        # AC14 — snapshot
        snap = svc.snapshot(
            {"universe_id": universe.universe_id, "label": "campaign_test", "campaign_id": "c1"}
        )
        assert snap["snapshot_id"]

        usage = svc.character_usage(universe.universe_id)
        assert usage["counts"].get("alex", 0) >= 1

        seen = {e.event_type for e in bus.history}
        assert EventType.UNIVERSE_UPDATED in seen
        assert EventType.MEMORY_CREATED in seen
        assert EventType.RELATIONSHIP_CREATED in seen or EventType.RELATIONSHIP_CHANGED in seen
        assert EventType.CANON_CONFLICT_DETECTED in seen
        assert EventType.CONTINUITY_WARNING in seen or EventType.CONTINUITY_FAILURE in seen
        assert EventType.UNIVERSE_SNAPSHOT_CREATED in seen
