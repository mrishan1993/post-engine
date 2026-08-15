from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


CanonStatus = Literal["canon", "provisional", "alternate", "non_canon", "contradicted", "retired"]
ContinuityResult = Literal["CONTINUITY_PASS", "CONTINUITY_WARNING", "CONTINUITY_FAIL"]
MemoryType = Literal["episodic", "semantic", "emotional", "relationship"]


class CreateUniverseRequest(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    rules: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    canon_mode: str = "canon"


class PersonalityScores(BaseModel):
    confidence: float = 0.35
    empathy: float = 0.5
    impulsiveness: float = 0.4
    humor: float = 0.7
    competitiveness: float = 0.4
    curiosity: float = 0.7
    patience: float = 0.4
    emotionality: float = 0.6


class CreateCharacterRequest(BaseModel):
    universe_id: str
    slug: str
    name: str
    description: str | None = None
    identity: dict[str, Any] = Field(default_factory=dict)
    personality: dict[str, Any] = Field(default_factory=dict)
    personality_scores: PersonalityScores | dict[str, Any] | None = None
    appearance: dict[str, Any] = Field(default_factory=dict)
    voice: dict[str, Any] = Field(default_factory=dict)
    behavioral_rules: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    status: str = "active"


class RecordEventRequest(BaseModel):
    universe_id: str
    description: str
    action: str | None = None
    participants: list[str] = Field(default_factory=list)  # character ids or slugs
    location: str | None = None
    episode_key: str | None = None
    story_id: str | None = None
    consequences: list[str] = Field(default_factory=list)
    emotional_impact: float = 0.5
    canon_status: CanonStatus = "provisional"
    create_memories: bool = True


class UpsertRelationshipRequest(BaseModel):
    universe_id: str
    source_id: str
    target_id: str
    relationship_type: str
    strength: float = 0.5
    traits: dict[str, float] = Field(default_factory=dict)
    canon_status: CanonStatus = "canon"
    evidence: dict[str, Any] = Field(default_factory=dict)


class AddCanonFactRequest(BaseModel):
    universe_id: str
    subject: str
    predicate: str
    object: str
    source: str | None = None
    confidence: float = 1.0
    status: CanonStatus = "canon"
    authority: str = "human"
    auto_detect_conflict: bool = True


class AddMemoryRequest(BaseModel):
    universe_id: str
    character_id: str
    text: str
    memory_type: MemoryType = "episodic"
    importance: float = 0.7
    emotional_weight: float = 0.5
    event_id: str | None = None
    canon_status: CanonStatus = "canon"


class CreateThreadRequest(BaseModel):
    universe_id: str
    description: str
    participants: list[str] = Field(default_factory=list)
    importance: float = 0.6
    audience_interest: float = 0.5
    potential_payoff: str | None = None


class AssembleContextRequest(BaseModel):
    universe_id: str
    character_slugs: list[str] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    premise: str | None = None
    include_audience_perception: bool = True
    memory_limit: int = 8
    campaign_id: str | None = None


class ValidateContinuityRequest(BaseModel):
    universe_id: str
    premise: str
    character_slugs: list[str] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    proposed_facts: list[dict[str, str]] = Field(default_factory=list)
    behavioral_actions: list[str] = Field(default_factory=list)


class UpdatePerceptionRequest(BaseModel):
    character_id: str
    universe_id: str | None = None
    perceived_traits: dict[str, Any] = Field(default_factory=dict)
    affinity: float | None = None
    sentiment: dict[str, Any] = Field(default_factory=dict)
    theories: list[str] = Field(default_factory=list)
    requests: list[str] = Field(default_factory=list)


class EvolveCharacterRequest(BaseModel):
    character_id: str
    personality_delta: dict[str, float] = Field(default_factory=dict)
    emotional_state: dict[str, Any] = Field(default_factory=dict)
    development_stage: str | None = None
    reason: str | None = None
    approved_by: str = "human"


class ResolveConflictRequest(BaseModel):
    conflict_id: str
    resolution: Literal["retcon", "keep_existing", "alternate", "human_note"] = "keep_existing"
    notes: str | None = None
    approved_by: str = "human"


class SnapshotRequest(BaseModel):
    universe_id: str
    label: str | None = None
    campaign_id: str | None = None
    episode_id: str | None = None


class CreativeContextOut(BaseModel):
    universe_id: str
    character_context: list[dict[str, Any]] = Field(default_factory=list)
    relationship_context: list[dict[str, Any]] = Field(default_factory=list)
    event_context: list[dict[str, Any]] = Field(default_factory=list)
    world_context: dict[str, Any] = Field(default_factory=dict)
    canon_constraints: list[dict[str, Any]] = Field(default_factory=list)
    visual_context: dict[str, Any] = Field(default_factory=dict)
    voice_context: dict[str, Any] = Field(default_factory=dict)
    audience_context: dict[str, Any] = Field(default_factory=dict)
    campaign_context: dict[str, Any] = Field(default_factory=dict)
    open_threads: list[dict[str, Any]] = Field(default_factory=list)
    memories: list[dict[str, Any]] = Field(default_factory=list)


class ContinuityReportOut(BaseModel):
    result: ContinuityResult
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)


class UniverseOut(BaseModel):
    universe_id: str
    slug: str
    name: str
    description: str | None = None
    status: str
    version: int
    canon_mode: str
    rules: dict[str, Any] = Field(default_factory=dict)


class CharacterOut(BaseModel):
    character_id: str
    universe_id: str | None
    slug: str
    name: str
    status: str
    version: int
    identity: dict[str, Any] = Field(default_factory=dict)
    personality: dict[str, Any] = Field(default_factory=dict)
    appearance: dict[str, Any] = Field(default_factory=dict)
    voice: dict[str, Any] = Field(default_factory=dict)
    behavioral_rules: list[str] = Field(default_factory=list)
    current_state: dict[str, Any] = Field(default_factory=dict)
