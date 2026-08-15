from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.settings import get_settings
from image_generation_engine.capabilities import get_image_provider_meta
from image_generation_engine.providers.base import (
    ImageGenerationProvider,
    ImageProviderStatus,
    ImageSubmitResult,
    PermanentImageError,
    TransientImageError,
)


class StubImageProvider(ImageGenerationProvider):
    """Provider A/B stub — writes local placeholder images (no live API)."""

    def __init__(
        self,
        name: str = "provider_a",
        *,
        fail_transient_times: int = 0,
        fail_permanent: bool = False,
    ):
        self.name = name
        self._meta = get_image_provider_meta(name) or {}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._fail_transient_times = fail_transient_times
        self._fail_permanent = fail_permanent
        self._transient_hits: dict[str, int] = {}

    def get_capabilities(self) -> dict[str, Any]:
        return {
            **(self._meta.get("capabilities") or {}),
            "limits": self._meta.get("limits") or {},
            "pricing": self._meta.get("pricing") or {},
            "model": self._meta.get("model"),
        }

    def health_check(self) -> bool:
        return bool(self._meta.get("enabled", True))

    def validate_request(self, request: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        gen = request.get("generation") or {}
        limits = self._meta.get("limits") or {}
        caps = self._meta.get("capabilities") or {}
        ratio = gen.get("aspect_ratio")
        if ratio and ratio not in (limits.get("supported_ratios") or []):
            issues.append(f"unsupported aspect_ratio {ratio}")
        res = gen.get("resolution")
        supported = limits.get("supported_resolutions") or []
        if res and supported and res not in supported:
            issues.append(f"unsupported resolution {res}")
        refs = request.get("references") or []
        max_refs = int(limits.get("max_references") or 99)
        if len(refs) > max_refs:
            issues.append(f"too many references ({len(refs)} > {max_refs})")
        mode = gen.get("mode") or "text_to_image"
        mode_cap = {
            "text_to_image": "text_to_image",
            "image_to_image": "image_to_image",
            "reference_to_image": "character_reference",
            "image_editing": "image_editing",
        }.get(mode, mode)
        if not caps.get(mode_cap, caps.get(mode, True)):
            issues.append(f"{mode} unsupported")
        if mode == "image_editing" and request.get("edit") and not caps.get("mask_editing"):
            if (request.get("edit") or {}).get("mask_asset_id"):
                issues.append("mask_editing unsupported")
        return issues

    def prepare_references(self, references: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared = []
        for ref in references:
            prepared.append(
                {
                    **ref,
                    "provider_asset_id": f"ref_{self.name}_{str(ref.get('asset_id', ''))[:8]}",
                    "status": "active",
                }
            )
        return prepared

    def estimate_cost(self, request: dict[str, Any]) -> float:
        return round(float((self._meta.get("pricing") or {}).get("cost_per_image") or 0.04), 6)

    def submit(self, request: dict[str, Any], *, seed: int | None = None) -> ImageSubmitResult:
        if self._fail_permanent:
            raise PermanentImageError("invalid_request: stub permanent failure")
        key = str((request.get("prompt") or {}).get("positive") or "")[:64]
        hits = self._transient_hits.get(key, 0)
        if hits < self._fail_transient_times:
            self._transient_hits[key] = hits + 1
            raise TransientImageError("provider_5xx: stub timeout")

        issues = self.validate_request(request)
        if issues:
            raise PermanentImageError("invalid_request: " + "; ".join(issues))

        job_id = f"{self.name}_{uuid4().hex[:12]}"
        uri = self._write_image(job_id, request, seed=seed)
        cost = self.estimate_cost(request)
        self._jobs[job_id] = {
            "status": "completed",
            "result_uri": uri,
            "actual_cost": round(cost * 0.95, 6),
            "request": request,
            "seed": seed,
        }
        return ImageSubmitResult(
            provider_job_id=job_id,
            estimated_cost=cost,
            metadata={"seed": seed, "model": self._meta.get("model")},
        )

    def get_status(self, provider_job_id: str) -> ImageProviderStatus:
        job = self._jobs.get(provider_job_id)
        if not job:
            return ImageProviderStatus(status="failed", error={"message": "unknown job"})
        return ImageProviderStatus(
            status=job["status"],
            result_uri=job.get("result_uri"),
            actual_cost=job.get("actual_cost"),
            metadata={"seed": job.get("seed")},
        )

    def _write_image(self, job_id: str, request: dict[str, Any], *, seed: int | None) -> str:
        settings = get_settings()
        root = Path(settings.storage_root) / "generated" / "image" / self.name
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{job_id}.png"
        gen = request.get("generation") or {}
        res = str(gen.get("resolution") or "1024x1536")
        w, h = 1024, 1536
        if "x" in res:
            parts = res.lower().split("x")
            try:
                w, h = int(parts[0]), int(parts[1])
            except ValueError:
                pass
        from amp_platform.procedural_media import infer_shot_label, materialize_png

        prompt = ((request.get("prompt") or {}).get("positive") or "")[:400]
        payload = {
            "stub": True,
            "procedural": True,
            "provider": self.name,
            "job_id": job_id,
            "seed": seed,
            "aspect_ratio": gen.get("aspect_ratio"),
            "width": w,
            "height": h,
            "mime_type": "image/png",
            "prompt": prompt,
            "mode": gen.get("mode"),
            "purpose": request.get("purpose"),
            "edit": request.get("edit"),
        }
        materialize_png(
            path,
            width=w,
            height=h,
            prompt=prompt,
            seed=seed,
            label=infer_shot_label(prompt),
        )
        path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")
        return str(path)
