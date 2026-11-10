"""Live video provider adapter for video_generation_engine."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from amp_platform.live_videos import available_video_backends, generate_video
from video_generation_engine.capabilities import get_video_provider_meta
from video_generation_engine.providers.base import (
    PermanentVideoError,
    VideoGenerationProvider,
    VideoProviderStatus,
    VideoSubmitResult,
)


class LiveVideoProvider(VideoGenerationProvider):
    def __init__(self, name: str = "provider_a", *, prefer: str | None = None):
        self.name = name
        self.prefer = prefer
        self._meta = get_video_provider_meta(name) or {}
        self._jobs: dict[str, dict[str, Any]] = {}

    def get_capabilities(self) -> dict[str, Any]:
        return {
            **(self._meta.get("capabilities") or {}),
            "limits": self._meta.get("limits") or {},
            "pricing": self._meta.get("pricing") or {},
            "model": self._meta.get("model"),
            "live_backends": available_video_backends(),
        }

    def health_check(self) -> bool:
        return bool(available_video_backends())

    def validate_request(self, request: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        if not ((request.get("prompt") or {}).get("positive") or "").strip():
            issues.append("missing prompt")
        if not available_video_backends():
            issues.append("no live video backend configured")
        return issues

    def prepare_references(self, references: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(references or [])

    def estimate_cost(self, request: dict[str, Any]) -> float:
        gen = request.get("generation") or {}
        dur = float(gen.get("duration_sec") or 5)
        return round(float((self._meta.get("pricing") or {}).get("cost_per_sec") or 0.08) * dur, 4)

    def submit(self, request: dict[str, Any], *, seed: int | None = None) -> VideoSubmitResult:
        issues = self.validate_request(request)
        if issues:
            raise PermanentVideoError("invalid_request: " + "; ".join(issues))
        prompt = ((request.get("prompt") or {}).get("positive") or "").strip()
        gen = request.get("generation") or {}
        dur = float(gen.get("duration_sec") or 5)
        job_id = f"{self.name}_{uuid4().hex[:12]}"
        try:
            path = generate_video(
                prompt,
                duration_sec=dur,
                seed=seed,
                prefer=self.prefer,
            )
        except Exception as exc:  # noqa: BLE001
            raise PermanentVideoError(str(exc)) from exc
        cost = self.estimate_cost(request)
        self._jobs[job_id] = {
            "status": "completed",
            "result_uri": str(path),
            "actual_cost": cost,
            "seed": seed,
        }
        return VideoSubmitResult(
            provider_job_id=job_id,
            estimated_cost=cost,
            metadata={"seed": seed, "live": True, "prefer": self.prefer},
        )

    def get_status(self, provider_job_id: str) -> VideoProviderStatus:
        job = self._jobs.get(provider_job_id)
        if not job:
            return VideoProviderStatus(status="failed", error={"message": "unknown job"})
        return VideoProviderStatus(
            status=job["status"],
            result_uri=job.get("result_uri"),
            actual_cost=job.get("actual_cost"),
            metadata={"seed": job.get("seed"), "live": True},
        )
