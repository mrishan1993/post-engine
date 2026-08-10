from __future__ import annotations

from typing import Any

from prompt_engine.adapters.base import ProviderAdapter
from prompt_engine.components import render_components
from prompt_engine.capabilities import PROVIDER_CAPABILITIES
from prompt_engine.schemas import CanonicalGenerationSpec, PromptPackageDoc


class VeoAdapter(ProviderAdapter):
    name = "veo"
    adapter_version = "1"

    def get_capabilities(self) -> dict[str, Any]:
        return dict(PROVIDER_CAPABILITIES["veo"]["capabilities"])

    def compile(self, spec: CanonicalGenerationSpec, *, components: list[str]) -> PromptPackageDoc:
        blocks = render_components(components)
        char = spec.subject.name or "the subject"
        loc = spec.environment.location_name or "the location"
        action = spec.subject.action or "moves"
        emotion = spec.subject.emotion or "tense"
        positive = (
            f"{spec.camera.shot_type.replace('_', ' ')} shot, {spec.camera.angle.replace('_', ' ')}, "
            f"{spec.camera.movement.replace('_', ' ')}. "
            f"{char} {action}, expression: {emotion}. "
            f"Environment: {loc}. "
            f"State: {', '.join(f'{k}={v}' for k, v in (spec.environment.state or {}).items()) or 'neutral'}. "
            f"Lighting: {spec.lighting}. Composition: {spec.composition}. "
            f"Objective: {spec.objective}. "
            + " ".join(blocks)
        )
        negative = (
            "identity drift, age change, extra limbs, text artifacts, watermark, "
            "cartoon unless requested, jumping cuts, invented props"
        )
        limits = self.get_capabilities().get("limits") or {}
        max_dur = float(limits.get("max_duration_sec") or 8)
        dur = min(spec.duration_sec, max_dur)
        refs = list(spec.references)[: int(limits.get("max_references") or 4)]
        return PromptPackageDoc(
            provider=self.name,
            model=str(self.get_capabilities().get("model")),
            modality=spec.modality,
            positive_prompt=positive.strip(),
            negative_prompt=negative,
            reference_assets=refs,
            parameters={
                "duration_sec": dur,
                "aspect_ratio": spec.aspect_ratio,
                "resolution": spec.resolution,
            },
            provider_options={
                "image_to_video": bool(refs),
                "preserve_identity": bool(spec.constraints.get("preserve_character_identity")),
                "adapter_version": self.adapter_version,
            },
            components_used=components,
        )
