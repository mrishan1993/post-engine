from __future__ import annotations

from typing import Any

from prompt_engine.adapters.base import ProviderAdapter
from prompt_engine.components import render_components
from prompt_engine.capabilities import PROVIDER_CAPABILITIES
from prompt_engine.schemas import CanonicalGenerationSpec, PromptPackageDoc


class RunwayAdapter(ProviderAdapter):
    name = "runway"
    adapter_version = "1"

    def get_capabilities(self) -> dict[str, Any]:
        return dict(PROVIDER_CAPABILITIES["runway"]["capabilities"])

    def compile(self, spec: CanonicalGenerationSpec, *, components: list[str]) -> PromptPackageDoc:
        blocks = render_components(components)
        # Runway-flavored structure (still stub text — not a live API call)
        motion_line = (
            f"Camera: {spec.camera.movement.replace('_', ' ')}; "
            f"shot: {spec.camera.shot_type}; angle: {spec.camera.angle}."
        )
        positive = (
            f"{spec.objective} "
            f"Subject: {spec.subject.name or 'character'} — {spec.subject.action}; "
            f"emotion {spec.subject.emotion}. "
            f"Scene: {spec.environment.location_name}. {motion_line} "
            + " ".join(blocks)
        )
        limits = self.get_capabilities().get("limits") or {}
        dur = min(spec.duration_sec, float(limits.get("max_duration_sec") or 10))
        refs = list(spec.references)[: int(limits.get("max_references") or 3)]
        return PromptPackageDoc(
            provider=self.name,
            model=str(self.get_capabilities().get("model")),
            modality=spec.modality,
            positive_prompt=positive.strip(),
            negative_prompt="warped face, identity change, flicker artifacts, extra fingers",
            reference_assets=refs,
            parameters={
                "duration_sec": dur,
                "aspect_ratio": spec.aspect_ratio,
                "motion_strength": (spec.motion or {}).get("intensity", "medium"),
            },
            provider_options={"adapter_version": self.adapter_version},
            components_used=components,
        )
