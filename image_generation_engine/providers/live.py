"""Live image provider adapter for image_generation_engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from amp_platform.live_images import available_image_backends, generate_image
from image_generation_engine.capabilities import get_image_provider_meta
from image_generation_engine.providers.base import (
    ImageGenerationProvider,
    ImageProviderStatus,
    ImageSubmitResult,
    PermanentImageError,
)


class LiveImageProvider(ImageGenerationProvider):
    def __init__(self, name: str = "provider_a", *, prefer: str | None = None):
        self.name = name
        self.prefer = prefer
        self._meta = get_image_provider_meta(name) or {}
        self._jobs: dict[str, dict[str, Any]] = {}

    def get_capabilities(self) -> dict[str, Any]:
        return {
            **(self._meta.get("capabilities") or {}),
            "limits": self._meta.get("limits") or {},
            "pricing": self._meta.get("pricing") or {},
            "model": self._meta.get("model"),
            "live_backends": available_image_backends(),
        }

    def health_check(self) -> bool:
        return bool(available_image_backends())

    def validate_request(self, request: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        if not ((request.get("prompt") or {}).get("positive") or "").strip():
            issues.append("missing prompt")
        if not available_image_backends():
            issues.append("no live image backend configured")
        return issues

    def prepare_references(self, references: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(references or [])

    def estimate_cost(self, request: dict[str, Any]) -> float:
        return float((self._meta.get("pricing") or {}).get("cost_per_image") or 0.04)

    def submit(self, request: dict[str, Any], *, seed: int | None = None) -> ImageSubmitResult:
        issues = self.validate_request(request)
        if issues:
            raise PermanentImageError("invalid_request: " + "; ".join(issues))
        prompt = ((request.get("prompt") or {}).get("positive") or "").strip()
        gen = request.get("generation") or {}
        res = str(gen.get("resolution") or "1080x1920")
        w, h = 1080, 1920
        if "x" in res.lower():
            try:
                parts = res.lower().split("x")
                w, h = int(parts[0]), int(parts[1])
            except ValueError:
                pass
        job_id = f"{self.name}_{uuid4().hex[:12]}"
        try:
            path = generate_image(
                prompt,
                width=w,
                height=h,
                seed=seed,
                prefer=self.prefer,
            )
        except Exception as exc:  # noqa: BLE001
            raise PermanentImageError(str(exc)) from exc
        cost = self.estimate_cost(request)
        self._jobs[job_id] = {
            "status": "completed",
            "result_uri": str(path),
            "actual_cost": cost,
            "seed": seed,
        }
        return ImageSubmitResult(
            provider_job_id=job_id,
            estimated_cost=cost,
            metadata={"seed": seed, "live": True, "prefer": self.prefer},
        )

    def get_status(self, provider_job_id: str) -> ImageProviderStatus:
        job = self._jobs.get(provider_job_id)
        if not job:
            return ImageProviderStatus(status="failed", error={"message": "unknown job"})
        return ImageProviderStatus(
            status=job["status"],
            result_uri=job.get("result_uri"),
            actual_cost=job.get("actual_cost"),
            metadata={"seed": job.get("seed"), "live": True},
        )
