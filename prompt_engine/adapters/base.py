from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from prompt_engine.schemas import CanonicalGenerationSpec, PromptPackageDoc, PromptValidationResult


class ProviderAdapter(ABC):
    name: str
    adapter_version: str = "1"

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def compile(self, spec: CanonicalGenerationSpec, *, components: list[str]) -> PromptPackageDoc:
        ...

    def validate(self, spec: CanonicalGenerationSpec, package: PromptPackageDoc) -> PromptValidationResult:
        caps = self.get_capabilities()
        issues: list[str] = []
        modality_caps = caps.get(spec.modality) or caps.get("video") or {}
        limits = caps.get("limits") or {}
        max_dur = limits.get("max_duration_sec")
        if max_dur is not None and spec.duration_sec > float(max_dur) + 0.05:
            issues.append(f"duration {spec.duration_sec}s exceeds provider max {max_dur}s")
        max_refs = limits.get("max_references")
        if max_refs is not None and len(package.reference_assets) > int(max_refs):
            issues.append(f"too many references ({len(package.reference_assets)} > {max_refs})")
        if spec.modality == "video" and not modality_caps.get("text_to_video", True):
            issues.append("provider lacks text_to_video")
        return PromptValidationResult(ok=not issues, structural=issues)

    def estimate_cost(self, spec: CanonicalGenerationSpec) -> float:
        caps = self.get_capabilities()
        if "cost_per_sec" in caps:
            return round(float(caps["cost_per_sec"]) * max(spec.duration_sec, 1.0), 6)
        if "cost_per_image" in caps:
            return float(caps["cost_per_image"])
        if "cost_per_track" in caps:
            return float(caps["cost_per_track"])
        if "cost_per_1k_chars" in caps:
            text = ((spec.narration or {}).get("text") or "") if spec.narration else ""
            return round(float(caps["cost_per_1k_chars"]) * (len(text) / 1000.0), 6)
        return 0.0

    def estimate_latency(self, spec: CanonicalGenerationSpec) -> float:
        caps = self.get_capabilities()
        base = float(caps.get("latency_base_sec") or 20)
        return round(base + 0.5 * spec.duration_sec, 3)
