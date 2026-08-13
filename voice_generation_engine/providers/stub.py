from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.settings import get_settings
from voice_generation_engine.capabilities import get_voice_provider_meta
from voice_generation_engine.providers.base import (
    PermanentVoiceError,
    TransientVoiceError,
    VoiceGenerationProvider,
    VoiceProviderStatus,
    VoiceSubmitResult,
)


class StubVoiceProvider(VoiceGenerationProvider):
    def __init__(
        self,
        name: str = "provider_a",
        *,
        fail_transient_times: int = 0,
        fail_permanent: bool = False,
    ):
        self.name = name
        self._meta = get_voice_provider_meta(name) or {}
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
        caps = self._meta.get("capabilities") or {}
        limits = self._meta.get("limits") or {}
        text = str(request.get("text") or "")
        if not text.strip():
            issues.append("empty script")
        if len(text) > int(limits.get("max_characters") or 5000):
            issues.append("script exceeds max_characters")
        lang = request.get("language") or "en"
        languages = caps.get("languages") or []
        if languages and lang not in languages and lang.split("-")[0] not in languages:
            if "hinglish" in languages and self._looks_hinglish(text):
                pass
            else:
                issues.append(f"unsupported language {lang}")
        if not caps.get("text_to_speech", True):
            issues.append("text_to_speech unsupported")
        if request.get("provider_voice_id") in {None, ""}:
            issues.append("missing provider_voice_id")
        return issues

    def estimate_cost(self, request: dict[str, Any]) -> float:
        text = str(request.get("text") or "")
        per_1k = float((self._meta.get("pricing") or {}).get("cost_per_1k_chars") or 0.03)
        return round(per_1k * max(len(text), 1) / 1000.0, 6)

    def submit(self, request: dict[str, Any], *, seed: int | None = None) -> VoiceSubmitResult:
        if self._fail_permanent:
            raise PermanentVoiceError("invalid_request: stub permanent failure")
        key = str(request.get("text") or "")[:64]
        hits = self._transient_hits.get(key, 0)
        if hits < self._fail_transient_times:
            self._transient_hits[key] = hits + 1
            raise TransientVoiceError("provider_5xx: stub timeout")

        issues = self.validate_request(request)
        if issues:
            raise PermanentVoiceError("invalid_request: " + "; ".join(issues))

        job_id = f"{self.name}_{uuid4().hex[:12]}"
        uri, meta = self._write_voice(job_id, request, seed=seed)
        cost = self.estimate_cost(request)
        self._jobs[job_id] = {
            "status": "completed",
            "result_uri": uri,
            "actual_cost": round(cost * 0.95, 6),
            "seed": seed,
            "timestamps": meta.get("timestamps"),
        }
        return VoiceSubmitResult(
            provider_job_id=job_id,
            estimated_cost=cost,
            metadata={"seed": seed, "model": self._meta.get("model"), **meta},
        )

    def get_status(self, provider_job_id: str) -> VoiceProviderStatus:
        job = self._jobs.get(provider_job_id)
        if not job:
            return VoiceProviderStatus(status="failed", error={"message": "unknown job"})
        return VoiceProviderStatus(
            status=job["status"],
            result_uri=job.get("result_uri"),
            actual_cost=job.get("actual_cost"),
            metadata={"seed": job.get("seed"), "timestamps": job.get("timestamps")},
        )

    def _write_voice(
        self, job_id: str, request: dict[str, Any], *, seed: int | None
    ) -> tuple[str, dict[str, Any]]:
        settings = get_settings()
        root = Path(settings.storage_root) / "generated" / "voice" / self.name
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{job_id}.wav"
        text = str(request.get("text") or "")
        delivery = request.get("delivery") or {}
        rate = float(delivery.get("speaking_rate") or 1.0)
        target = request.get("target_duration_sec")
        timestamps = self._word_timestamps(text, rate, request.get("pauses") or [])
        duration = float(target) if target else (
            timestamps[-1]["end"] if timestamps else 1.0
        )
        payload = {
            "stub": True,
            "provider": self.name,
            "job_id": job_id,
            "seed": seed,
            "text": text[:800],
            "provider_voice_id": request.get("provider_voice_id"),
            "language": request.get("language"),
            "delivery": delivery,
            "duration_sec": round(duration, 3),
            "sample_rate": 48000,
            "channels": 1,
            "loudness_lufs": -16.0,
            "true_peak_db": -1.5,
            "mime_type": "audio/wav",
            "timestamps": {"words": timestamps},
            "phonemes": [],
        }
        path.write_bytes(b"AMP_VOICE_STUB\n" + json.dumps(payload, indent=2).encode("utf-8"))
        path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")
        return str(path), {"timestamps": payload["timestamps"], "duration_sec": duration}

    def _word_timestamps(
        self, text: str, rate: float, pauses: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        words = re.findall(r"\S+", text)
        if not words:
            return []
        pause_map: dict[str, float] = {}
        for p in pauses:
            key = (p.get("after_word") or p.get("after") or "").strip(".,!?\"'")
            if key:
                pause_map[key.lower()] = float(p.get("duration_ms") or 0) / 1000.0
        word_dur = 0.38 / max(rate, 0.4)
        t = 0.1
        out = []
        for w in words:
            clean = w.strip(".,!?\"'")
            start = round(t, 3)
            end = round(t + word_dur, 3)
            out.append({"word": clean, "start": start, "end": end})
            t = end + 0.04
            if clean.lower() in pause_map:
                t += pause_map[clean.lower()]
        return out

    @staticmethod
    def _looks_hinglish(text: str) -> bool:
        hindi_markers = ("hai", "kya", "nahi", "mujhe", "bro", "yaar")
        return any(m in text.lower() for m in hindi_markers)
