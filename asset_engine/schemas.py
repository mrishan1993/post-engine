from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AssetStatus = Literal["draft", "approved", "active", "deprecated", "archived"]


class CanonRules(BaseModel):
    immutable: list[str] = Field(default_factory=lambda: ["face", "personality_core"])
    flexible: list[str] = Field(
        default_factory=lambda: ["clothing", "facial_expression", "pose", "environment"]
    )
    forbidden: list[str] = Field(
        default_factory=lambda: ["changing species", "changing age band", "changing gender"]
    )


class CharacterCanonical(BaseModel):
    identity: dict[str, Any] = Field(default_factory=dict)
    personality: dict[str, Any] = Field(default_factory=dict)
    appearance: dict[str, Any] = Field(default_factory=dict)
    behavioral_rules: list[str] = Field(default_factory=list)
    voice: dict[str, Any] = Field(default_factory=dict)
    visual_style: dict[str, Any] = Field(default_factory=dict)
    canon: CanonRules = Field(default_factory=CanonRules)
    prompt_instructions: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class SceneRequest(BaseModel):
    character_slug: str | None = None
    character_id: str | None = None
    character_version: int | None = None
    location: str | None = None
    emotion: str | None = None
    action: str | None = None
    prop: str | None = None
    style: str | None = None
    platform: str = "youtube_shorts"
    duration_sec: int = 30
    camera: dict[str, Any] = Field(default_factory=dict)


class GenerationContext(BaseModel):
    character: dict[str, Any] = Field(default_factory=dict)
    references: list[dict[str, Any]] = Field(default_factory=list)
    location: dict[str, Any] | None = None
    props: list[dict[str, Any]] = Field(default_factory=list)
    style: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None
    world: dict[str, Any] | None = None
    memory: list[dict[str, Any]] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    selection_scores: dict[str, float] = Field(default_factory=dict)
