from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ScriptAgentConfig(BaseModel):
    system_prompt_template: str
    content_source: Literal["public_domain", "original_generation"]
    tone: str
    max_script_length_words: int = 150


class AudioAgentConfig(BaseModel):
    type: Literal["music", "narration"]
    provider: str
    style_prompt: str
    voice_id: str | None = None


class VisualAgentConfig(BaseModel):
    type: Literal["fixed_rig", "generative"]
    rig_path: str | None = None
    generative_prompt_template: str | None = None

    @model_validator(mode="after")
    def validate_type_fields(self) -> VisualAgentConfig:
        if self.type == "fixed_rig" and not self.rig_path:
            raise ValueError("fixed_rig visual agent requires rig_path")
        if self.type == "generative" and not self.generative_prompt_template:
            raise ValueError("generative visual agent requires generative_prompt_template")
        return self


class AssemblyAgentConfig(BaseModel):
    intro_template: str
    outro_template: str
    caption_style: str
    target_resolution: str = "1080x1920"
    target_duration_sec_max: int = 60


class PublishingAgentConfig(BaseModel):
    platforms: list[Literal["youtube", "instagram"]]
    youtube_made_for_kids: bool
    youtube_category: str
    posting_cadence: str


class SafetyQAConfig(BaseModel):
    classifier_thresholds: dict[str, float]
    human_review_required: bool = True

    @field_validator("human_review_required")
    @classmethod
    def enforce_human_review(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("human_review_required cannot be disabled")
        return value


class VerticalConfig(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str
    script_agent: ScriptAgentConfig
    audio_agent: AudioAgentConfig
    visual_agent: VisualAgentConfig
    assembly_agent: AssemblyAgentConfig
    publishing_agent: PublishingAgentConfig
    safety_qa: SafetyQAConfig
