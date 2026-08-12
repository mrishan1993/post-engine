from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.settings import get_settings
from generation_engine.providers.base import (
    GenerationProvider,
    PermanentGenerationError,
    ProviderStatus,
    SubmitResult,
    TransientGenerationError,
)
from prompt_engine.capabilities import PROVIDER_CAPABILITIES


class StubGenerationProvider(GenerationProvider):
    """Local filesystem stub — no external API calls."""

    def __init__(
        self,
        name: str,
        *,
        fail_transient_times: int = 0,
        fail_permanent: bool = False,
    ):
        self.name = name
        meta = PROVIDER_CAPABILITIES.get(name, {})
        self.modalities = list(meta.get("modalities") or ["video"])
        self._caps = dict(meta.get("capabilities") or {})
        self._jobs: dict[str, dict[str, Any]] = {}
        self._fail_transient_times = fail_transient_times
        self._fail_permanent = fail_permanent
        self._transient_hits: dict[str, int] = {}

    def get_capabilities(self) -> dict[str, Any]:
        return dict(self._caps)

    def health_check(self) -> bool:
        return True

    def estimate_cost(self, prompt_package: dict[str, Any]) -> float:
        params = prompt_package.get("parameters") or {}
        dur = float(params.get("duration_sec") or 4)
        if "cost_per_sec" in self._caps:
            return round(float(self._caps["cost_per_sec"]) * dur, 6)
        if "cost_per_image" in self._caps:
            return float(self._caps["cost_per_image"])
        if "cost_per_track" in self._caps:
            return float(self._caps["cost_per_track"])
        if "cost_per_1k_chars" in self._caps:
            text = prompt_package.get("positive_prompt") or ""
            return round(float(self._caps["cost_per_1k_chars"]) * (len(text) / 1000.0), 6)
        return 0.05

    def submit(
        self,
        prompt_package: dict[str, Any],
        *,
        seed: int | None = None,
        references: list[dict[str, Any]] | None = None,
    ) -> SubmitResult:
        if self._fail_permanent:
            raise PermanentGenerationError("invalid_request: stub permanent failure")

        job_id = f"{self.name}_{uuid4().hex[:12]}"
        if self._fail_transient_times:
            hits = self._transient_hits.get(job_id, 0)
            # Count by submit attempts keyed loosely — use prompt hash
            key = hashlib.md5(
                (prompt_package.get("positive_prompt") or "").encode()
            ).hexdigest()[:8]
            hits = self._transient_hits.get(key, 0)
            if hits < self._fail_transient_times:
                self._transient_hits[key] = hits + 1
                raise TransientGenerationError("provider_5xx: stub timeout")

        modality = prompt_package.get("modality") or self.modalities[0]
        cost = self.estimate_cost(prompt_package)
        self._jobs[job_id] = {
            "status": "processing",
            "created": time.time(),
            "prompt_package": prompt_package,
            "seed": seed,
            "references": references or [],
            "modality": modality,
            "actual_cost": cost * 0.95,
            "result_uri": None,
        }
        # Complete synchronously for Phase-0 stub (poll will see completed)
        uri = self._materialize(job_id, prompt_package, modality=modality, seed=seed)
        self._jobs[job_id]["status"] = "completed"
        self._jobs[job_id]["result_uri"] = uri
        return SubmitResult(
            provider_job_id=job_id,
            status="submitted",
            estimated_cost=cost,
            metadata={"seed": seed, "model": self._caps.get("model")},
        )

    def get_status(self, provider_job_id: str) -> ProviderStatus:
        job = self._jobs.get(provider_job_id)
        if not job:
            return ProviderStatus(status="failed", error={"message": "unknown job"})
        return ProviderStatus(
            status=job["status"],
            progress=1.0 if job["status"] == "completed" else 0.5,
            result_uri=job.get("result_uri"),
            actual_cost=job.get("actual_cost"),
            metadata={"seed": job.get("seed"), "modality": job.get("modality")},
        )

    def _materialize(
        self,
        job_id: str,
        prompt_package: dict[str, Any],
        *,
        modality: str,
        seed: int | None,
    ) -> str:
        settings = get_settings()
        root = Path(settings.storage_root) / "generated" / self.name
        root.mkdir(parents=True, exist_ok=True)
        ext = {
            "video": "mp4",
            "image": "png",
            "thumbnail": "png",
            "voice": "wav",
            "music": "mp3",
            "sfx": "wav",
        }.get(modality, "bin")
        path = root / f"{job_id}.{ext}"
        payload = {
            "provider": self.name,
            "job_id": job_id,
            "modality": modality,
            "seed": seed,
            "prompt": (prompt_package.get("positive_prompt") or "")[:500],
            "parameters": prompt_package.get("parameters") or {},
            "stub": True,
        }
        # Minimal valid-ish placeholder bytes (not a real media container)
        body = ("AMP_STUB_ARTIFACT\n" + json.dumps(payload, indent=2)).encode("utf-8")
        path.write_bytes(body)
        return str(path)
