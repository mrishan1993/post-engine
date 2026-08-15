from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.settings import get_settings
from video_generation_engine.capabilities import get_video_provider_meta
from video_generation_engine.providers.base import (
    PermanentVideoError,
    TransientVideoError,
    VideoGenerationProvider,
    VideoProviderStatus,
    VideoSubmitResult,
)


class StubVideoProvider(VideoGenerationProvider):
    """Provider A/B stub — writes local placeholder clips (no live API)."""

    def __init__(
        self,
        name: str = "provider_a",
        *,
        fail_transient_times: int = 0,
        fail_permanent: bool = False,
    ):
        self.name = name
        self._meta = get_video_provider_meta(name) or {}
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
        dur = float(gen.get("duration_sec") or 0)
        if dur < float(limits.get("min_duration_sec") or 0):
            issues.append(f"duration below min ({dur})")
        if dur > float(limits.get("max_duration_sec") or 999):
            issues.append(f"duration above max ({dur})")
        ratio = gen.get("aspect_ratio")
        if ratio and ratio not in (limits.get("supported_ratios") or []):
            issues.append(f"unsupported aspect_ratio {ratio}")
        refs = request.get("references") or []
        max_refs = int(limits.get("max_references") or 99)
        if len(refs) > max_refs:
            issues.append(f"too many references ({len(refs)} > {max_refs})")
        mode = gen.get("mode") or "text_to_video"
        caps = self._meta.get("capabilities") or {}
        if mode == "image_to_video" and not caps.get("image_to_video"):
            issues.append("image_to_video unsupported")
        if mode == "reference_to_video" and not caps.get("character_reference"):
            issues.append("reference_to_video unsupported")
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
        dur = float((request.get("generation") or {}).get("duration_sec") or 4)
        cps = float((self._meta.get("pricing") or {}).get("cost_per_sec") or 0.08)
        return round(cps * dur, 6)

    def submit(self, request: dict[str, Any], *, seed: int | None = None) -> VideoSubmitResult:
        if self._fail_permanent:
            raise PermanentVideoError("invalid_request: stub permanent failure")
        key = str((request.get("prompt") or {}).get("positive") or "")[:64]
        hits = self._transient_hits.get(key, 0)
        if hits < self._fail_transient_times:
            self._transient_hits[key] = hits + 1
            raise TransientVideoError("provider_5xx: stub timeout")

        issues = self.validate_request(request)
        if issues:
            raise PermanentVideoError("invalid_request: " + "; ".join(issues))

        job_id = f"{self.name}_{uuid4().hex[:12]}"
        uri = self._write_clip(job_id, request, seed=seed)
        cost = self.estimate_cost(request)
        self._jobs[job_id] = {
            "status": "completed",
            "result_uri": uri,
            "actual_cost": round(cost * 0.95, 6),
            "request": request,
            "seed": seed,
        }
        return VideoSubmitResult(
            provider_job_id=job_id,
            estimated_cost=cost,
            metadata={"seed": seed, "model": self._meta.get("model")},
        )

    def get_status(self, provider_job_id: str) -> VideoProviderStatus:
        job = self._jobs.get(provider_job_id)
        if not job:
            return VideoProviderStatus(status="failed", error={"message": "unknown job"})
        return VideoProviderStatus(
            status=job["status"],
            result_uri=job.get("result_uri"),
            actual_cost=job.get("actual_cost"),
            metadata={"seed": job.get("seed")},
        )

    def _write_clip(self, job_id: str, request: dict[str, Any], *, seed: int | None) -> str:
        settings = get_settings()
        root = Path(settings.storage_root) / "generated" / "video" / self.name
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{job_id}.mp4"
        gen = request.get("generation") or {}
        # Parse resolution for metadata stamped into stub
        res = str(gen.get("resolution") or "1080x1920")
        w, h = 1080, 1920
        if "x" in res:
            parts = res.lower().split("x")
            try:
                w, h = int(parts[0]), int(parts[1])
            except ValueError:
                pass
        from amp_platform.procedural_media import (
            infer_shot_label,
            materialize_mp4,
            materialize_png,
            resolve_ffmpeg,
        )

        prompt = ((request.get("prompt") or {}).get("positive") or "")[:400]
        dur = float(gen.get("duration_sec") or 2.5)
        fps = int(gen.get("fps") or 30)
        payload = {
            "stub": True,
            "procedural": True,
            "provider": self.name,
            "job_id": job_id,
            "seed": seed,
            "duration_sec": dur,
            "aspect_ratio": gen.get("aspect_ratio"),
            "width": w,
            "height": h,
            "fps": fps,
            "prompt": prompt,
            "mode": gen.get("mode"),
            "camera": request.get("camera"),
            "video_codec": "h264",
            "mime_type": "video/mp4",
        }
        label = infer_shot_label(prompt)
        if resolve_ffmpeg():
            materialize_mp4(
                path,
                width=w,
                height=h,
                duration_sec=dur,
                prompt=prompt,
                seed=seed,
                label=label,
                text=prompt.strip().split("\n")[0][:42] if prompt else None,
            )
        else:
            still = path.with_suffix(".png")
            materialize_png(still, width=w, height=h, prompt=prompt, seed=seed, label=label)
            # Without ffmpeg, keep meta so QA can probe; leave a real PNG path referenced
            path.write_bytes(still.read_bytes())
        path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")
        return str(path)
