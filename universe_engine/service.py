from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from asset_engine.characters import CharacterRegistry
from asset_engine.schemas import CharacterCanonical, CanonRules
from universe_engine.context import build_visual_context, build_voice_context, rank_memories
from universe_engine.continuity import (
    behavioral_conflict,
    canon_predicate_conflict,
    detect_first_meet_claim,
    score_memory_recall,
)
from universe_engine.schemas import (
    AddCanonFactRequest,
    AddMemoryRequest,
    AssembleContextRequest,
    CharacterOut,
    ContinuityReportOut,
    CreateCharacterRequest,
    CreateThreadRequest,
    CreateUniverseRequest,
    CreativeContextOut,
    EvolveCharacterRequest,
    PersonalityScores,
    RecordEventRequest,
    ResolveConflictRequest,
    SnapshotRequest,
    UniverseOut,
    UpdatePerceptionRequest,
    UpsertRelationshipRequest,
    ValidateContinuityRequest,
)
from db.models import (
    CanonFact,
    Character,
    CharacterAppearance,
    CharacterPerception,
    CharacterState,
    ContinuityConflict,
    CreativeDecision,
    CreativeMemory,
    StoryThread,
    Universe,
    UniverseEntity,
    UniverseEvent,
    UniverseRelationship,
    UniverseSnapshot,
)


class UniverseService:
    """Character & Content Universe Intelligence — memory, identity, continuity."""

    def __init__(self, session: Session):
        self.session = session
        self.chars = CharacterRegistry(session)

    # ── Universe ─────────────────────────────────────────────────────────────

    def create_universe(self, request: CreateUniverseRequest | dict[str, Any]) -> UniverseOut:
        req = (
            request
            if isinstance(request, CreateUniverseRequest)
            else CreateUniverseRequest.model_validate(request)
        )
        slug = req.slug or req.name.lower().replace(" ", "_")[:64]
        existing = self.session.scalar(select(Universe).where(Universe.slug == slug))
        if existing:
            raise ValueError(f"universe slug exists: {slug}")
        row = Universe(
            id=str(uuid4()),
            slug=slug,
            name=req.name,
            description=req.description,
            rules=req.rules or {"technology": "contemporary", "tone": "comedic_drama"},
            status=req.status,
            version=1,
            canon_mode=req.canon_mode,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        self._log(row.id, None, {"action": "universe_created", "name": row.name}, reason="bootstrap")
        get_bus().publish(
            EventType.UNIVERSE_UPDATED,
            {"universe_id": row.id, "slug": row.slug, "version": row.version},
            producer="universe-engine",
        )
        return self._universe_out(row)

    def get_universe(self, universe_id: str) -> UniverseOut:
        return self._universe_out(self._get_universe(universe_id))

    # ── Characters ───────────────────────────────────────────────────────────

    def create_character(self, request: CreateCharacterRequest | dict[str, Any]) -> CharacterOut:
        req = (
            request
            if isinstance(request, CreateCharacterRequest)
            else CreateCharacterRequest.model_validate(request)
        )
        universe = self._get_universe(req.universe_id)
        scores = (
            req.personality_scores
            if isinstance(req.personality_scores, PersonalityScores)
            else PersonalityScores.model_validate(req.personality_scores or {})
        )
        personality = dict(req.personality or {})
        personality.setdefault("scores", scores.model_dump())
        personality.setdefault("traits", list(personality.get("traits") or []))
        identity = {
            "occupation": None,
            "origin": None,
            "location": None,
            "background": None,
            **(req.identity or {}),
            "name": req.name,
        }
        appearance = {
            "immutable_traits": ["facial_structure", "signature_features"],
            "mutable_traits": ["clothing", "accessories"],
            **(req.appearance or {}),
        }
        voice = {
            "formality": "casual",
            "humor": "sarcastic",
            "sentence_length": "short",
            "slang": True,
            "language_preferences": ["en", "hinglish"],
            **(req.voice or {}),
        }
        rules = list(req.behavioral_rules or [])
        if not rules:
            rules = [
                "Uses humor under stress.",
                "Overthinks decisions.",
                "Avoids confrontation when possible.",
            ]
        canonical = CharacterCanonical(
            identity=identity,
            personality=personality,
            appearance=appearance,
            behavioral_rules=rules,
            voice=voice,
            visual_style={},
            canon=CanonRules(),
            prompt_instructions=[],
            extra={"goals": req.goals, "fears": req.fears},
        )
        char = self.chars.create(
            slug=req.slug,
            name=req.name,
            canonical=canonical,
            description=req.description,
            universe_id=universe.id,
            status=req.status,
        )
        state = CharacterState(
            id=str(uuid4()),
            character_id=char.id,
            emotional_state={"primary": "anxious", "anxiety": 0.4},
            goals=req.goals or ["grow"],
            fears=req.fears or ["public_embarrassment"],
            relationships_snapshot={},
            unresolved_conflicts=[],
            recent_events=[],
            development_stage="introduction",
            personality_scores=scores.model_dump(),
            effective_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(state)
        self.session.flush()
        # Seed identity canon facts
        if identity.get("occupation"):
            self.add_canon_fact(
                AddCanonFactRequest(
                    universe_id=universe.id,
                    subject=char.slug,
                    predicate="works_as",
                    object=str(identity["occupation"]),
                    source="character_create",
                    authority="system",
                    auto_detect_conflict=False,
                )
            )
        get_bus().publish(
            EventType.CHARACTER_STATE_CHANGED,
            {"character_id": char.id, "development_stage": state.development_stage},
            producer="universe-engine",
        )
        self._log(
            universe.id,
            char.id,
            {"action": "character_created", "slug": char.slug},
            reason="structured character bootstrap",
        )
        return self._character_out(char)

    def get_character(self, character_id: str) -> CharacterOut:
        char = self.session.get(Character, character_id)
        if not char:
            raise ValueError(f"character not found: {character_id}")
        return self._character_out(char)

    def evolve_character(self, request: EvolveCharacterRequest | dict[str, Any]) -> CharacterOut:
        req = (
            request
            if isinstance(request, EvolveCharacterRequest)
            else EvolveCharacterRequest.model_validate(request)
        )
        char = self.session.get(Character, req.character_id)
        if not char:
            raise ValueError(f"character not found: {req.character_id}")
        prev = self._latest_state(char.id)
        scores = dict((prev.personality_scores if prev else None) or {})
        for k, delta in (req.personality_delta or {}).items():
            scores[k] = round(min(1.0, max(0.0, float(scores.get(k, 0.5)) + float(delta))), 3)
        state = CharacterState(
            id=str(uuid4()),
            character_id=char.id,
            emotional_state=req.emotional_state or (prev.emotional_state if prev else {}),
            goals=prev.goals if prev else [],
            fears=prev.fears if prev else [],
            relationships_snapshot=prev.relationships_snapshot if prev else {},
            unresolved_conflicts=prev.unresolved_conflicts if prev else [],
            recent_events=prev.recent_events if prev else [],
            development_stage=req.development_stage
            or (prev.development_stage if prev else "developing"),
            personality_scores=scores,
            effective_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(state)
        # Mirror scores into canonical personality
        data = dict(char.canonical_data or {})
        personality = dict(data.get("personality") or {})
        personality["scores"] = scores
        data["personality"] = personality
        self.chars.bump_version(char.id, data, change_log=req.reason or "evolution", activate=True)
        self._log(
            char.universe_id,
            char.id,
            {"action": "character_evolved", "scores": scores},
            reason=req.reason,
            approved_by=req.approved_by,
        )
        get_bus().publish(
            EventType.CHARACTER_STATE_CHANGED,
            {"character_id": char.id, "personality_scores": scores},
            producer="universe-engine",
        )
        get_bus().publish(
            EventType.CHARACTER_VERSIONED,
            {"character_id": char.id, "version": char.current_version},
            producer="universe-engine",
        )
        self.session.flush()
        return self._character_out(char)

    # ── Relationships / Events / Memories / Canon ────────────────────────────

    def upsert_relationship(
        self, request: UpsertRelationshipRequest | dict[str, Any]
    ) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, UpsertRelationshipRequest)
            else UpsertRelationshipRequest.model_validate(request)
        )
        src = self._resolve_character(req.source_id)
        tgt = self._resolve_character(req.target_id)
        existing = self.session.scalar(
            select(UniverseRelationship).where(
                UniverseRelationship.universe_id == req.universe_id,
                UniverseRelationship.source_id == src.id,
                UniverseRelationship.target_id == tgt.id,
                UniverseRelationship.end_time.is_(None),
            )
        )
        now = datetime.now(timezone.utc)
        if existing:
            history = list(existing.history or [])
            history.append(
                {
                    "at": now.isoformat(),
                    "from_type": existing.relationship_type,
                    "from_strength": float(existing.strength or 0),
                }
            )
            existing.relationship_type = req.relationship_type
            existing.strength = req.strength
            existing.traits = req.traits
            existing.canon_status = req.canon_status
            existing.evidence = req.evidence
            existing.history = history
            existing.updated_at = now
            row = existing
            get_bus().publish(
                EventType.RELATIONSHIP_CHANGED,
                {
                    "relationship_id": row.id,
                    "type": row.relationship_type,
                    "strength": float(row.strength or 0),
                },
                producer="universe-engine",
            )
        else:
            row = UniverseRelationship(
                id=str(uuid4()),
                universe_id=req.universe_id,
                source_type="character",
                source_id=src.id,
                target_type="character",
                target_id=tgt.id,
                relationship_type=req.relationship_type,
                strength=req.strength,
                traits=req.traits,
                start_time=now,
                canon_status=req.canon_status,
                evidence=req.evidence,
                history=[{"at": now.isoformat(), "type": req.relationship_type, "stage": "created"}],
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
            get_bus().publish(
                EventType.RELATIONSHIP_CREATED,
                {
                    "relationship_id": row.id,
                    "source_id": src.id,
                    "target_id": tgt.id,
                    "type": row.relationship_type,
                },
                producer="universe-engine",
            )
        self.session.flush()
        return {
            "relationship_id": row.id,
            "source_id": src.id,
            "target_id": tgt.id,
            "type": row.relationship_type,
            "strength": float(row.strength or 0),
            "history": row.history,
        }

    def record_event(self, request: RecordEventRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, RecordEventRequest)
            else RecordEventRequest.model_validate(request)
        )
        participant_ids = []
        for p in req.participants:
            try:
                participant_ids.append(self._resolve_character(p).id)
            except ValueError:
                participant_ids.append(p)
        event = UniverseEvent(
            id=str(uuid4()),
            universe_id=req.universe_id,
            story_id=req.story_id,
            episode_key=req.episode_key,
            timestamp=datetime.now(timezone.utc),
            participants=participant_ids,
            location=req.location,
            action=req.action,
            description=req.description,
            consequences=req.consequences,
            emotional_impact=req.emotional_impact,
            affected_relationships=[],
            canon_status=req.canon_status,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(event)
        self.session.flush()
        get_bus().publish(
            EventType.EVENT_CREATED,
            {"event_id": event.id, "universe_id": req.universe_id, "episode_key": req.episode_key},
            producer="universe-engine",
        )
        if req.canon_status == "canon":
            get_bus().publish(
                EventType.EVENT_CANONIZED,
                {"event_id": event.id},
                producer="universe-engine",
            )

        memories = []
        if req.create_memories:
            for cid in participant_ids:
                if not self.session.get(Character, cid):
                    continue
                mem_type = "emotional" if req.emotional_impact >= 0.7 else "episodic"
                importance = min(1.0, 0.4 + float(req.emotional_impact))
                mem = self.add_memory(
                    AddMemoryRequest(
                        universe_id=req.universe_id,
                        character_id=cid,
                        text=req.description,
                        memory_type=mem_type,  # type: ignore[arg-type]
                        importance=importance,
                        emotional_weight=float(req.emotional_impact),
                        event_id=event.id,
                        canon_status=req.canon_status,  # type: ignore[arg-type]
                    )
                )
                memories.append(mem)
                # Update character state recent events / anxiety bump
                prev = self._latest_state(cid)
                recent = list((prev.recent_events if prev else None) or [])
                recent.append({"event_id": event.id, "description": req.description})
                emo = dict((prev.emotional_state if prev else None) or {})
                if "embarrass" in req.description.lower() or "anxiety" in (req.action or "").lower():
                    emo["anxiety"] = min(1.0, float(emo.get("anxiety") or 0.3) + 0.1)
                state = CharacterState(
                    id=str(uuid4()),
                    character_id=cid,
                    emotional_state=emo,
                    goals=prev.goals if prev else [],
                    fears=prev.fears if prev else [],
                    relationships_snapshot=prev.relationships_snapshot if prev else {},
                    unresolved_conflicts=prev.unresolved_conflicts if prev else [],
                    recent_events=recent[-10:],
                    development_stage=prev.development_stage if prev else "active",
                    personality_scores=prev.personality_scores if prev else {},
                    effective_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                )
                self.session.add(state)
                # Track appearance
                self.session.add(
                    CharacterAppearance(
                        id=str(uuid4()),
                        character_id=cid,
                        universe_id=req.universe_id,
                        episode_key=req.episode_key,
                        content_id=req.story_id,
                        role="participant",
                        appeared_at=datetime.now(timezone.utc),
                    )
                )
                get_bus().publish(
                    EventType.CHARACTER_STATE_CHANGED,
                    {"character_id": cid, "event_id": event.id},
                    producer="universe-engine",
                )

        # Auto open thread for unresolved consequences
        for c in req.consequences:
            if any(w in c.lower() for w in ("unresolved", "missing", "why", "?")):
                self.create_thread(
                    CreateThreadRequest(
                        universe_id=req.universe_id,
                        description=c,
                        participants=participant_ids,
                        importance=0.7,
                    )
                )

        self.session.flush()
        return {
            "event_id": event.id,
            "canon_status": event.canon_status,
            "memories": memories,
            "consequences": req.consequences,
        }

    def add_memory(self, request: AddMemoryRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, AddMemoryRequest)
            else AddMemoryRequest.model_validate(request)
        )
        recall = score_memory_recall(
            importance=req.importance,
            emotional_weight=req.emotional_weight,
            recency=1.0,
        )
        row = CreativeMemory(
            id=str(uuid4()),
            universe_id=req.universe_id,
            character_id=req.character_id,
            event_id=req.event_id,
            memory_type=req.memory_type,
            text=req.text,
            importance=req.importance,
            emotional_weight=req.emotional_weight,
            recency=1.0,
            recall_probability=recall,
            canon_status=req.canon_status,
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.MEMORY_CREATED,
            {
                "memory_id": row.id,
                "character_id": row.character_id,
                "memory_type": row.memory_type,
                "importance": float(row.importance or 0),
            },
            producer="universe-engine",
        )
        return {
            "memory_id": row.id,
            "text": row.text,
            "memory_type": row.memory_type,
            "importance": float(row.importance or 0),
            "recall_probability": float(row.recall_probability or 0),
        }

    def add_canon_fact(self, request: AddCanonFactRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, AddCanonFactRequest)
            else AddCanonFactRequest.model_validate(request)
        )
        existing = [
            {
                "id": f.id,
                "subject": f.subject,
                "predicate": f.predicate,
                "object": f.object,
                "status": f.status,
                "source": f.source,
            }
            for f in self.session.scalars(
                select(CanonFact).where(CanonFact.universe_id == req.universe_id)
            ).all()
        ]
        conflict_id = None
        if req.auto_detect_conflict:
            conflict = canon_predicate_conflict(
                existing, req.subject, req.predicate, req.object
            )
            if conflict:
                conflict_id = self._store_conflict(req.universe_id, conflict)
                get_bus().publish(
                    EventType.CANON_CONFLICT_DETECTED,
                    {"conflict_id": conflict_id, "universe_id": req.universe_id},
                    producer="universe-engine",
                )
                # Do not silently choose — leave proposed as provisional
                status = "provisional"
            else:
                status = req.status
        else:
            status = req.status

        row = CanonFact(
            id=str(uuid4()),
            universe_id=req.universe_id,
            subject=req.subject,
            predicate=req.predicate,
            object=req.object,
            source=req.source,
            confidence=req.confidence,
            status=status,
            authority=req.authority,
            version=1,
            evidence={"lineage": True, "source": req.source},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.CANON_CREATED,
            {
                "fact_id": row.id,
                "subject": row.subject,
                "predicate": row.predicate,
                "status": row.status,
            },
            producer="universe-engine",
        )
        return {
            "fact_id": row.id,
            "status": row.status,
            "conflict_id": conflict_id,
            "subject": row.subject,
            "predicate": row.predicate,
            "object": row.object,
            "source": row.source,
        }

    def retcon_fact(
        self,
        fact_id: str,
        *,
        new_object: str,
        reason: str,
        approved_by: str = "human",
    ) -> dict[str, Any]:
        fact = self.session.get(CanonFact, fact_id)
        if not fact:
            raise ValueError(f"fact not found: {fact_id}")
        old = fact.object
        fact.status = "retired"
        fact.updated_at = datetime.now(timezone.utc)
        new = CanonFact(
            id=str(uuid4()),
            universe_id=fact.universe_id,
            subject=fact.subject,
            predicate=fact.predicate,
            object=new_object,
            source=f"retcon:{fact.id}",
            confidence=1.0,
            status="canon",
            authority=approved_by,
            version=int(fact.version or 1) + 1,
            evidence={"retired_fact_id": fact.id, "previous_object": old, "reason": reason},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(new)
        self._log(
            fact.universe_id,
            fact.id,
            {"action": "retcon", "from": old, "to": new_object},
            reason=reason,
            approved_by=approved_by,
        )
        get_bus().publish(
            EventType.CANON_RETCONNED,
            {"old_fact_id": fact.id, "new_fact_id": new.id},
            producer="universe-engine",
        )
        self.session.flush()
        return {"retired_fact_id": fact.id, "new_fact_id": new.id, "object": new_object}

    def create_thread(self, request: CreateThreadRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, CreateThreadRequest)
            else CreateThreadRequest.model_validate(request)
        )
        row = StoryThread(
            id=str(uuid4()),
            universe_id=req.universe_id,
            description=req.description,
            participants=req.participants,
            importance=req.importance,
            audience_interest=req.audience_interest,
            status="active",
            potential_payoff=req.potential_payoff,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.STORY_THREAD_CREATED,
            {"thread_id": row.id, "description": row.description},
            producer="universe-engine",
        )
        return {"thread_id": row.id, "status": row.status, "description": row.description}

    def resolve_thread(self, thread_id: str) -> dict[str, Any]:
        row = self.session.get(StoryThread, thread_id)
        if not row:
            raise ValueError(f"thread not found: {thread_id}")
        row.status = "resolved"
        row.updated_at = datetime.now(timezone.utc)
        get_bus().publish(
            EventType.STORY_THREAD_RESOLVED,
            {"thread_id": row.id},
            producer="universe-engine",
        )
        self.session.flush()
        return {"thread_id": row.id, "status": row.status}

    # ── Context / Continuity / Snapshots ─────────────────────────────────────

    def assemble_context(
        self, request: AssembleContextRequest | dict[str, Any]
    ) -> CreativeContextOut:
        req = (
            request
            if isinstance(request, AssembleContextRequest)
            else AssembleContextRequest.model_validate(request)
        )
        universe = self._get_universe(req.universe_id)
        characters = self._resolve_many(req.character_ids, req.character_slugs)
        char_ctx = []
        visual: dict[str, Any] = {}
        voice: dict[str, Any] = {}
        audience_ctx: dict[str, Any] = {}
        for char in characters:
            data = dict(char.canonical_data or {})
            state = self._latest_state(char.id)
            char_ctx.append(
                {
                    "character_id": char.id,
                    "slug": char.slug,
                    "name": char.name,
                    "identity": data.get("identity"),
                    "personality": data.get("personality"),
                    "behavioral_rules": data.get("behavioral_rules"),
                    "current_state": {
                        "emotional_state": state.emotional_state if state else {},
                        "goals": state.goals if state else [],
                        "fears": state.fears if state else [],
                        "development_stage": state.development_stage if state else None,
                        "personality_scores": state.personality_scores if state else {},
                        "recent_events": (state.recent_events if state else [])[-5:],
                    },
                }
            )
            visual[char.slug] = build_visual_context(data)
            voice[char.slug] = build_voice_context(data)
            if req.include_audience_perception:
                perc = self.session.scalar(
                    select(CharacterPerception)
                    .where(CharacterPerception.character_id == char.id)
                    .order_by(CharacterPerception.updated_at.desc())
                )
                if perc:
                    audience_ctx[char.slug] = {
                        "perceived_traits": perc.perceived_traits,
                        "affinity": float(perc.affinity or 0),
                        "sentiment": perc.sentiment,
                        "theories": perc.theories,
                        "requests": perc.requests,
                        "note": "audience perception — not canon",
                    }

        char_ids = {c.id for c in characters}
        rels = []
        for r in self.session.scalars(
            select(UniverseRelationship).where(
                UniverseRelationship.universe_id == universe.id,
                UniverseRelationship.end_time.is_(None),
            )
        ).all():
            if r.source_id in char_ids or r.target_id in char_ids or not char_ids:
                rels.append(
                    {
                        "relationship_id": r.id,
                        "source_id": r.source_id,
                        "target_id": r.target_id,
                        "type": r.relationship_type,
                        "strength": float(r.strength or 0),
                        "traits": r.traits,
                        "history_len": len(r.history or []),
                    }
                )

        events = [
            {
                "event_id": e.id,
                "description": e.description,
                "episode_key": e.episode_key,
                "participants": e.participants,
                "canon_status": e.canon_status,
            }
            for e in self.session.scalars(
                select(UniverseEvent)
                .where(UniverseEvent.universe_id == universe.id)
                .order_by(UniverseEvent.created_at.desc())
                .limit(10)
            ).all()
            if not char_ids or any(p in char_ids for p in (e.participants or []))
        ]

        mem_rows = list(
            self.session.scalars(
                select(CreativeMemory).where(
                    CreativeMemory.universe_id == universe.id,
                    CreativeMemory.status == "active",
                )
            ).all()
        )
        if char_ids:
            mem_rows = [m for m in mem_rows if m.character_id in char_ids]
        memories = rank_memories(
            [
                {
                    "memory_id": m.id,
                    "character_id": m.character_id,
                    "text": m.text,
                    "memory_type": m.memory_type,
                    "importance": float(m.importance or 0),
                    "recall_probability": float(m.recall_probability or 0),
                }
                for m in mem_rows
            ],
            limit=req.memory_limit,
            premise=req.premise,
        )

        canon = [
            {
                "fact_id": f.id,
                "subject": f.subject,
                "predicate": f.predicate,
                "object": f.object,
                "status": f.status,
                "source": f.source,
            }
            for f in self.session.scalars(
                select(CanonFact).where(
                    CanonFact.universe_id == universe.id,
                    CanonFact.status.in_(["canon", "provisional"]),
                )
            ).all()
        ]

        threads = [
            {
                "thread_id": t.id,
                "description": t.description,
                "importance": float(t.importance or 0),
                "status": t.status,
            }
            for t in self.session.scalars(
                select(StoryThread).where(
                    StoryThread.universe_id == universe.id,
                    StoryThread.status.in_(["active", "developing"]),
                )
            ).all()
        ]

        campaign_ctx: dict[str, Any] = {}
        if req.campaign_id:
            campaign_ctx = {"campaign_id": req.campaign_id}

        return CreativeContextOut(
            universe_id=universe.id,
            character_context=char_ctx,
            relationship_context=rels,
            event_context=events,
            world_context={"rules": universe.rules or {}, "canon_mode": universe.canon_mode},
            canon_constraints=canon,
            visual_context=visual,
            voice_context=voice,
            audience_context=audience_ctx,
            campaign_context=campaign_ctx,
            open_threads=threads,
            memories=memories,
        )

    def validate_continuity(
        self, request: ValidateContinuityRequest | dict[str, Any]
    ) -> ContinuityReportOut:
        req = (
            request
            if isinstance(request, ValidateContinuityRequest)
            else ValidateContinuityRequest.model_validate(request)
        )
        characters = self._resolve_many(req.character_ids, req.character_slugs)
        warnings: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        conflict_ids: list[str] = []

        # First-meet vs relationship history
        if detect_first_meet_claim(req.premise) and len(characters) >= 2:
            a, b = characters[0], characters[1]
            prior = list(
                self.session.scalars(
                    select(UniverseRelationship).where(
                        UniverseRelationship.universe_id == req.universe_id,
                        UniverseRelationship.source_id.in_([a.id, b.id]),
                        UniverseRelationship.target_id.in_([a.id, b.id]),
                    )
                ).all()
            )
            # Count shared events
            shared_events = 0
            for e in self.session.scalars(
                select(UniverseEvent).where(UniverseEvent.universe_id == req.universe_id)
            ).all():
                parts = set(e.participants or [])
                if a.id in parts and b.id in parts:
                    shared_events += 1
            interactions = shared_events + sum(len(r.history or []) for r in prior)
            if interactions > 0 or prior:
                issue = {
                    "conflict_type": "relationship_history",
                    "severity": "warning",
                    "description": (
                        f"CONTINUITY_WARNING: premise claims first meeting but "
                        f"history indicates {max(interactions, len(prior))} prior interactions"
                    ),
                    "proposed": {"premise": req.premise},
                    "existing": {
                        "shared_events": shared_events,
                        "relationships": [r.relationship_type for r in prior],
                    },
                    "suggested_revision": "Meet again after prior shared history / argument",
                }
                warnings.append(issue)
                conflict_ids.append(self._store_conflict(req.universe_id, issue))
                get_bus().publish(
                    EventType.CONTINUITY_WARNING,
                    {"universe_id": req.universe_id, "issue": issue["description"]},
                    producer="universe-engine",
                )

        # Behavioral rules
        for char in characters:
            rules = list((char.canonical_data or {}).get("behavioral_rules") or [])
            for issue in behavioral_conflict(rules, req.behavioral_actions):
                cid = self._store_conflict(req.universe_id, issue)
                conflict_ids.append(cid)
                if issue["severity"] == "fail":
                    failures.append(issue)
                    get_bus().publish(
                        EventType.CONTINUITY_FAILURE,
                        {"universe_id": req.universe_id, "conflict_id": cid},
                        producer="universe-engine",
                    )
                else:
                    warnings.append(issue)
                    get_bus().publish(
                        EventType.CONTINUITY_WARNING,
                        {"universe_id": req.universe_id, "conflict_id": cid},
                        producer="universe-engine",
                    )

        # Proposed facts vs canon
        existing_facts = [
            {
                "id": f.id,
                "subject": f.subject,
                "predicate": f.predicate,
                "object": f.object,
                "status": f.status,
                "source": f.source,
            }
            for f in self.session.scalars(
                select(CanonFact).where(CanonFact.universe_id == req.universe_id)
            ).all()
        ]
        for pf in req.proposed_facts:
            conflict = canon_predicate_conflict(
                existing_facts,
                pf.get("subject", ""),
                pf.get("predicate", ""),
                pf.get("object", ""),
            )
            if conflict:
                cid = self._store_conflict(req.universe_id, conflict)
                conflict_ids.append(cid)
                failures.append(conflict)
                get_bus().publish(
                    EventType.CANON_CONFLICT_DETECTED,
                    {"conflict_id": cid, "universe_id": req.universe_id},
                    producer="universe-engine",
                )
                get_bus().publish(
                    EventType.CONTINUITY_FAILURE,
                    {"universe_id": req.universe_id, "conflict_id": cid},
                    producer="universe-engine",
                )

        if failures:
            result = "CONTINUITY_FAIL"
        elif warnings:
            result = "CONTINUITY_WARNING"
        else:
            result = "CONTINUITY_PASS"
        self.session.flush()
        return ContinuityReportOut(
            result=result,  # type: ignore[arg-type]
            warnings=warnings,
            failures=failures,
            conflict_ids=conflict_ids,
        )

    def resolve_conflict(
        self, request: ResolveConflictRequest | dict[str, Any]
    ) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, ResolveConflictRequest)
            else ResolveConflictRequest.model_validate(request)
        )
        row = self.session.get(ContinuityConflict, req.conflict_id)
        if not row:
            raise ValueError(f"conflict not found: {req.conflict_id}")
        row.status = "resolved"
        row.resolution = {
            "resolution": req.resolution,
            "notes": req.notes,
            "approved_by": req.approved_by,
        }
        self._log(
            row.universe_id,
            row.id,
            {"action": "conflict_resolved", "resolution": req.resolution},
            reason=req.notes,
            approved_by=req.approved_by,
        )
        self.session.flush()
        return {"conflict_id": row.id, "status": row.status, "resolution": row.resolution}

    def snapshot(self, request: SnapshotRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, SnapshotRequest)
            else SnapshotRequest.model_validate(request)
        )
        universe = self._get_universe(req.universe_id)
        ctx = self.assemble_context(
            AssembleContextRequest(universe_id=universe.id, include_audience_perception=True)
        )
        chars = list(
            self.session.scalars(
                select(Character).where(Character.universe_id == universe.id)
            ).all()
        )
        payload = {
            "universe": self._universe_out(universe).model_dump(mode="json"),
            "characters": [self._character_out(c).model_dump(mode="json") for c in chars],
            "context": ctx.model_dump(mode="json"),
            "usage": self.character_usage(universe.id),
        }
        row = UniverseSnapshot(
            id=str(uuid4()),
            universe_id=universe.id,
            campaign_id=req.campaign_id,
            episode_id=req.episode_id,
            label=req.label or f"v{universe.version}",
            snapshot=payload,
            version=universe.version,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.UNIVERSE_SNAPSHOT_CREATED,
            {"snapshot_id": row.id, "universe_id": universe.id, "version": row.version},
            producer="universe-engine",
        )
        return {"snapshot_id": row.id, "version": row.version, "label": row.label}

    def update_perception(
        self, request: UpdatePerceptionRequest | dict[str, Any]
    ) -> dict[str, Any]:
        """Audience perception — kept separate from canon."""
        req = (
            request
            if isinstance(request, UpdatePerceptionRequest)
            else UpdatePerceptionRequest.model_validate(request)
        )
        row = CharacterPerception(
            id=str(uuid4()),
            character_id=req.character_id,
            universe_id=req.universe_id,
            perceived_traits=req.perceived_traits,
            affinity=req.affinity,
            sentiment=req.sentiment,
            theories=req.theories,
            requests=req.requests,
            source="audience",
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.CHARACTER_AFFINITY_CHANGED,
            {
                "character_id": req.character_id,
                "affinity": req.affinity,
                "source": "audience_perception",
            },
            producer="universe-engine",
        )
        # Expansion signal if affinity high + requests
        if (req.affinity or 0) >= 80 and req.requests:
            get_bus().publish(
                EventType.CHARACTER_EXPANSION_DETECTED,
                {
                    "character_id": req.character_id,
                    "affinity": req.affinity,
                    "requests": req.requests,
                },
                producer="universe-engine",
            )
        return {
            "perception_id": row.id,
            "character_id": row.character_id,
            "affinity": float(row.affinity or 0),
            "note": "perception is not canon",
        }

    def character_usage(self, universe_id: str) -> dict[str, Any]:
        chars = list(
            self.session.scalars(
                select(Character).where(Character.universe_id == universe_id)
            ).all()
        )
        total = 0
        counts: dict[str, int] = {}
        for c in chars:
            n = int(
                self.session.scalar(
                    select(func.count())
                    .select_from(CharacterAppearance)
                    .where(CharacterAppearance.character_id == c.id)
                )
                or 0
            )
            counts[c.slug] = n
            total += n
        balance = {
            slug: round(n / total, 3) if total else 0.0 for slug, n in counts.items()
        }
        fatigue = [slug for slug, share in balance.items() if share >= 0.4]
        return {"counts": counts, "share": balance, "fatigue_candidates": fatigue, "total": total}

    def add_entity(
        self,
        *,
        universe_id: str,
        type: str,
        name: str,
        attributes: dict[str, Any] | None = None,
        slug: str | None = None,
    ) -> dict[str, Any]:
        row = UniverseEntity(
            id=str(uuid4()),
            universe_id=universe_id,
            type=type,
            name=name,
            slug=slug or name.lower().replace(" ", "_"),
            attributes=attributes or {},
            status="active",
            canon_status="canon",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        return {"entity_id": row.id, "type": row.type, "name": row.name}

    # ── Internals ────────────────────────────────────────────────────────────

    def _get_universe(self, universe_id: str) -> Universe:
        row = self.session.get(Universe, universe_id)
        if not row:
            raise ValueError(f"universe not found: {universe_id}")
        return row

    def _resolve_character(self, id_or_slug: str) -> Character:
        char = self.session.get(Character, id_or_slug) or self.chars.by_slug(id_or_slug)
        if not char:
            raise ValueError(f"character not found: {id_or_slug}")
        return char

    def _resolve_many(self, ids: list[str], slugs: list[str]) -> list[Character]:
        out: list[Character] = []
        seen: set[str] = set()
        for x in list(ids) + list(slugs):
            try:
                c = self._resolve_character(x)
            except ValueError:
                continue
            if c.id not in seen:
                seen.add(c.id)
                out.append(c)
        return out

    def _latest_state(self, character_id: str) -> CharacterState | None:
        return self.session.scalar(
            select(CharacterState)
            .where(CharacterState.character_id == character_id)
            .order_by(CharacterState.created_at.desc())
        )

    def _store_conflict(self, universe_id: str, issue: dict[str, Any]) -> str:
        row = ContinuityConflict(
            id=str(uuid4()),
            universe_id=universe_id,
            severity=issue.get("severity") or "warning",
            conflict_type=issue.get("conflict_type") or "unknown",
            description=issue.get("description"),
            proposed=issue.get("proposed"),
            existing=issue.get("existing"),
            suggested_revision=issue.get("suggested_revision"),
            status="open",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        return row.id

    def _log(
        self,
        universe_id: str | None,
        entity_id: str | None,
        change: dict[str, Any],
        *,
        reason: str | None = None,
        approved_by: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            CreativeDecision(
                id=str(uuid4()),
                universe_id=universe_id,
                entity_id=entity_id,
                change=change,
                reason=reason,
                source="universe_engine",
                evidence=evidence,
                approved_by=approved_by,
                model_version="universe_v1",
                created_at=datetime.now(timezone.utc),
            )
        )

    def _universe_out(self, row: Universe) -> UniverseOut:
        return UniverseOut(
            universe_id=row.id,
            slug=row.slug,
            name=row.name,
            description=row.description,
            status=row.status,
            version=int(row.version or 1),
            canon_mode=row.canon_mode or "canon",
            rules=row.rules or {},
        )

    def _character_out(self, char: Character) -> CharacterOut:
        data = dict(char.canonical_data or {})
        state = self._latest_state(char.id)
        return CharacterOut(
            character_id=char.id,
            universe_id=char.universe_id,
            slug=char.slug,
            name=char.name,
            status=char.status,
            version=int(char.current_version or 1),
            identity=data.get("identity") or {},
            personality=data.get("personality") or {},
            appearance=data.get("appearance") or {},
            voice=data.get("voice") or {},
            behavioral_rules=list(data.get("behavioral_rules") or []),
            current_state={
                "emotional_state": state.emotional_state if state else {},
                "goals": state.goals if state else [],
                "fears": state.fears if state else [],
                "development_stage": state.development_stage if state else None,
                "personality_scores": state.personality_scores if state else {},
            },
        )
