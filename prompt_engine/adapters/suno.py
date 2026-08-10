from __future__ import annotations

from typing import Any

from prompt_engine.adapters.base import ProviderAdapter
from prompt_engine.capabilities import PROVIDER_CAPABILITIES
from prompt_engine.schemas import CanonicalGenerationSpec, PromptPackageDoc


class SunoAdapter(ProviderAdapter):
    name = "suno"
    adapter_version = "1"

    def get_capabilities(self) -> dict[str, Any]:
        return dict(PROVIDER_CAPABILITIES["suno"]["capabilities"])

    def compile(self, spec: CanonicalGenerationSpec, *, components: list[str]) -> PromptPackageDoc:
        music = spec.music or spec.audio or {}
        mood = music.get("mood") or "ominous"
        genre = music.get("genre") or "cinematic_horror"
        tempo = music.get("tempo_bpm") or music.get("target_bpm") or 78
        instrumentation = music.get("instrumentation") or ["low_drone", "strings", "sub_bass"]
        energy = music.get("energy_curve") or {"0": 0.2, "50": 0.6, "100": 0.3}
        positive = (
            f"Instrumental {genre} score, mood {mood}, tempo ~{tempo} BPM, "
            f"instruments: {', '.join(instrumentation)}. Duration {spec.duration_sec}s. "
            f"Energy curve {energy}. No vocals."
        )
        return PromptPackageDoc(
            provider=self.name,
            model=str(self.get_capabilities().get("model")),
            modality="music",
            positive_prompt=positive,
            negative_prompt="pop vocals, lyrics, upbeat dance",
            reference_assets=[],
            parameters={
                "mood": mood,
                "genre": genre,
                "tempo_bpm": tempo,
                "instrumentation": instrumentation,
                "energy_curve": energy,
                "duration_sec": spec.duration_sec,
                "vocals": False,
            },
            provider_options={"adapter_version": self.adapter_version, "components": components},
            components_used=components,
        )
