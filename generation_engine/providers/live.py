"""Live adapters for generation_engine (veo / runway / gpt_image)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from amp_platform.live_images import available_image_backends, generate_image
from amp_platform.live_videos import available_video_backends, generate_video
from generation_engine.providers.base import (
    GenerationProvider,
    PermanentGenerationError,
    ProviderStatus,
    SubmitResult,
)
from prompt_engine.capabilities import PROVIDER_CAPABILITIES


class LiveGenerationProvider(GenerationProvider):
    def __init__(self, name: str):
        self.name = name
        meta = PROVIDER_CAPABILITIES.get(name, {})
        self.modalities = list(meta.get("modalities") or ["video"])
        self._caps = dict(meta.get("capabilities") or {})
        self._jobs: dict[str, dict[str, Any]] = {}

    def get_capabilities(self) -> dict[str, Any]:
        return dict(self._caps)

    def health_check(self) -> bool:
        if "image" in self.modalities or "thumbnail" in self.modalities:
            return bool(available_image_backends())
        if "video" in self.modalities:
            return bool(available_video_backends())
        return False

    def estimate_cost(self, prompt_package: dict[str, Any]) -> float:
        params = prompt_package.get("parameters") or {}
        if "image" in self.modalities or prompt_package.get("modality") in {"image", "thumbnail"}:
            return float(self._caps.get("cost_per_image") or 0.04)
        dur = float(params.get("duration_sec") or 4)
        return round(float(self._caps.get("cost_per_sec") or 0.08) * dur, 6)

    def submit(
        self,
        prompt_package: dict[str, Any],
        *,
        seed: int | None = None,
        references: list[dict[str, Any]] | None = None,
    ) -> SubmitResult:
        _ = references
        prompt = (prompt_package.get("positive_prompt") or "").strip()
        if not prompt:
            raise PermanentGenerationError("missing positive_prompt")
        modality = prompt_package.get("modality") or self.modalities[0]
        params = prompt_package.get("parameters") or {}
        job_id = f"{self.name}_{uuid4().hex[:12]}"
        try:
            if modality in {"image", "thumbnail"}:
                prefer = "openai" if self.name == "gpt_image" else "fal"
                path = generate_image(
                    prompt,
                    width=int(params.get("width") or 1080),
                    height=int(params.get("height") or 1920),
                    seed=seed,
                    prefer=prefer,
                )
            else:
                prefer = "runway" if self.name == "runway" else "google_veo"
                path = generate_video(
                    prompt,
                    duration_sec=float(params.get("duration_sec") or 5),
                    seed=seed,
                    prefer=prefer,
                )
        except Exception as exc:  # noqa: BLE001
            raise PermanentGenerationError(str(exc)) from exc

        cost = self.estimate_cost(prompt_package)
        self._jobs[job_id] = {
            "status": "completed",
            "result_uri": str(path),
            "actual_cost": cost * 0.95,
            "seed": seed,
            "modality": modality,
        }
        return SubmitResult(
            provider_job_id=job_id,
            status="submitted",
            estimated_cost=cost,
            metadata={"seed": seed, "live": True, "model": self._caps.get("model")},
        )

    def get_status(self, provider_job_id: str) -> ProviderStatus:
        job = self._jobs.get(provider_job_id)
        if not job:
            return ProviderStatus(status="failed", error={"message": "unknown job"})
        return ProviderStatus(
            status=job["status"],
            progress=1.0,
            result_uri=job.get("result_uri"),
            actual_cost=job.get("actual_cost"),
            metadata={"seed": job.get("seed"), "modality": job.get("modality"), "live": True},
        )
