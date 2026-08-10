from __future__ import annotations

from typing import Any

from prompt_engine.adapters.base import ProviderAdapter
from prompt_engine.components import render_components
from prompt_engine.capabilities import PROVIDER_CAPABILITIES
from prompt_engine.schemas import CanonicalGenerationSpec, PromptPackageDoc


class GptImageAdapter(ProviderAdapter):
    name = "gpt_image"
    adapter_version = "1"

    def get_capabilities(self) -> dict[str, Any]:
        return dict(PROVIDER_CAPABILITIES["gpt_image"]["capabilities"])

    def compile(self, spec: CanonicalGenerationSpec, *, components: list[str]) -> PromptPackageDoc:
        purpose = spec.image_purpose or "storyboard_frame"
        blocks = render_components(components)
        positive = (
            f"Purpose: {purpose}. {spec.objective} "
            f"{spec.subject.name or 'subject'} — {spec.subject.emotion}; "
            f"{spec.camera.shot_type} composition; {spec.environment.location_name}. "
            + " ".join(blocks)
        )
        return PromptPackageDoc(
            provider=self.name,
            model=str(self.get_capabilities().get("model")),
            modality="image" if spec.modality == "thumbnail" else spec.modality,
            positive_prompt=positive.strip(),
            negative_prompt="blurry, deformed, watermark, text clutter",
            reference_assets=list(spec.references)[:4],
            parameters={
                "aspect_ratio": spec.aspect_ratio,
                "purpose": purpose,
            },
            provider_options={"adapter_version": self.adapter_version},
            components_used=components,
        )
