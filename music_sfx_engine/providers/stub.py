from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.settings import get_settings
from music_sfx_engine.capabilities import get_music_provider_meta
from music_sfx_engine.providers.base import (
    MusicGenerationProvider,
    MusicProviderStatus,
    MusicSubmitResult,
    PermanentMusicError,
    TransientMusicError,
)


class StubMusicProvider(MusicGenerationProvider):
    def __init__(
        self,
        name: str = "provider_a",
        *,
        fail_transient_times: int = 0,
        fail_permanent: bool = False,
    ):
        self.name = name
        self._meta = get_music_provider_meta(name) or {}
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
        limits = self._meta.get("limits") or {}
        caps = self._meta.get("capabilities") or {}
        dur = float(request.get("duration_sec") or 0)
        if dur < float(limits.get("min_duration_sec") or 0):
            issues.append(f"duration below min ({dur})")
        if dur > float(limits.get("max_duration_sec") or 999):
            issues.append(f"duration above max ({dur})")
        genre = request.get("genre")
        genres = caps.get("genres") or []
        if genre and genres and genre not in genres:
            issues.append(f"unsupported genre {genre}")
        if request.get("vocals_enabled") and not caps.get("vocals"):
            issues.append("vocals unsupported")
        if not caps.get("text_to_music", True):
            issues.append("text_to_music unsupported")
        return issues

    def estimate_cost(self, request: dict[str, Any]) -> float:
        return round(
            float((self._meta.get("pricing") or {}).get("cost_per_generation") or 0.1), 6
        )

    def submit(self, request: dict[str, Any], *, seed: int | None = None) -> MusicSubmitResult:
        if self._fail_permanent:
            raise PermanentMusicError("invalid_request: stub permanent failure")
        key = str(request.get("prompt") or request.get("genre") or "")[:64]
        hits = self._transient_hits.get(key, 0)
        if hits < self._fail_transient_times:
            self._transient_hits[key] = hits + 1
            raise TransientMusicError("provider_5xx: stub timeout")

        issues = self.validate_request(request)
        if issues:
            raise PermanentMusicError("invalid_request: " + "; ".join(issues))

        job_id = f"{self.name}_{uuid4().hex[:12]}"
        uri = self._write_audio(job_id, request, seed=seed)
        cost = self.estimate_cost(request)
        self._jobs[job_id] = {
            "status": "completed",
            "result_uri": uri,
            "actual_cost": round(cost * 0.95, 6),
            "seed": seed,
        }
        return MusicSubmitResult(
            provider_job_id=job_id,
            estimated_cost=cost,
            metadata={"seed": seed, "model": self._meta.get("model")},
        )

    def get_status(self, provider_job_id: str) -> MusicProviderStatus:
        job = self._jobs.get(provider_job_id)
        if not job:
            return MusicProviderStatus(status="failed", error={"message": "unknown job"})
        return MusicProviderStatus(
            status=job["status"],
            result_uri=job.get("result_uri"),
            actual_cost=job.get("actual_cost"),
            metadata={"seed": job.get("seed")},
        )

    def _write_audio(self, job_id: str, request: dict[str, Any], *, seed: int | None) -> str:
        settings = get_settings()
        root = Path(settings.storage_root) / "generated" / "music" / self.name
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{job_id}.wav"
        bpm = float(request.get("tempo_bpm") or 82)
        duration = float(request.get("duration_sec") or 30)
        beat_interval = 60.0 / bpm
        beats = [round(i * beat_interval, 3) for i in range(int(duration / beat_interval) + 1)]
        payload = {
            "stub": True,
            "provider": self.name,
            "job_id": job_id,
            "seed": seed,
            "duration_sec": duration,
            "sample_rate": 44100,
            "channels": 2,
            "loudness_lufs": -14.0,
            "true_peak_db": -1.0,
            "mime_type": "audio/wav",
            "genre": request.get("genre"),
            "mood": request.get("mood"),
            "tempo_bpm": bpm,
            "beat_grid": beats[:200],
            "segments": request.get("segments") or [],
            "prompt": str(request.get("prompt") or "")[:400],
        }
        path.write_bytes(b"AMP_AUDIO_STUB\n" + json.dumps(payload, indent=2).encode("utf-8"))
        path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")
        return str(path)
