from __future__ import annotations

from typing import Any

from prompt_engine.adapters.base import ProviderAdapter
from prompt_engine.capabilities import PROVIDER_CAPABILITIES
from prompt_engine.schemas import CanonicalGenerationSpec, PromptPackageDoc


class ElevenLabsAdapter(ProviderAdapter):
    name = "elevenlabs"
    adapter_version = "1"

    def get_capabilities(self) -> dict[str, Any]:
        return dict(PROVIDER_CAPABILITIES["elevenlabs"]["capabilities"])

    def compile(self, spec: CanonicalGenerationSpec, *, components: list[str]) -> PromptPackageDoc:
        text = ""
        if spec.narration:
            text = str(spec.narration.get("text") or "")
        emotion = spec.subject.emotion or "neutral"
        intensity = float((spec.audio or {}).get("intensity") or 0.7)
        voice_package = {
            "voice_profile_id": (spec.subject.immutable or {}).get("voice_profile_id"),
            "text": text,
            "emotion": emotion,
            "intensity": intensity,
            "pace": "slow" if emotion in {"fear", "unease"} else "medium",
            "emphasis": [],
        }
        if text:
            words = text.split()
            if words:
                voice_package["emphasis"] = [words[0].strip(".,!?\"'").lower()]
        return PromptPackageDoc(
            provider=self.name,
            model=str(self.get_capabilities().get("model")),
            modality="voice",
            positive_prompt=text,
            negative_prompt="",
            reference_assets=[],
            parameters=voice_package,
            provider_options={"adapter_version": self.adapter_version, "components": components},
            components_used=components,
        )
