from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from voice_generation_engine.schemas import TechnicalVoiceQA


def probe_voice(uri: str) -> dict[str, Any]:
    path = Path(uri)
    meta_path = path.with_suffix(".meta.json")
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return {
            "source": "stub",
            "duration_sec": data.get("duration_sec"),
            "sample_rate": data.get("sample_rate") or 48000,
            "channels": data.get("channels") or 1,
            "loudness_lufs": data.get("loudness_lufs"),
            "true_peak_db": data.get("true_peak_db"),
            "timestamps": data.get("timestamps"),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
    return {"source": "none", "size_bytes": path.stat().st_size if path.exists() else 0}


def validate_voice_artifact(
    uri: str,
    *,
    expected_duration: float | None = None,
    duration_tolerance: float = 1.25,
) -> TechnicalVoiceQA:
    path = Path(uri)
    notes: list[str] = []
    exists = path.exists() and path.is_file()
    if not exists:
        return TechnicalVoiceQA(ok=False, file_exists=False, notes=["file missing"])

    raw = path.read_bytes()
    readable = len(raw) > 0
    if not readable:
        return TechnicalVoiceQA(ok=False, file_exists=True, readable=False, notes=["empty file"])

    probed = probe_voice(uri)
    source = str(probed.get("source") or "none")
    clipping_risk = False
    silence_risk = False
    corruption_risk = False

    if raw.startswith(b"AMP_VOICE_STUB"):
        notes.append("stub artifact accepted")
    elif source == "none":
        notes.append("no probe metadata; basic checks only")
        corruption_risk = len(raw) < 16

    duration_ok = True
    if expected_duration is not None and probed.get("duration_sec") is not None:
        duration_ok = abs(float(probed["duration_sec"]) - float(expected_duration)) <= duration_tolerance
        if not duration_ok:
            notes.append(
                f"duration mismatch expected={expected_duration} got={probed['duration_sec']}"
            )

    sample_rate_ok = True
    sr = probed.get("sample_rate")
    if sr is not None and int(sr) < 16000:
        sample_rate_ok = False
        notes.append(f"low sample rate {sr}")

    peak = probed.get("true_peak_db")
    if peak is not None and float(peak) > 0:
        clipping_risk = True
        notes.append("true peak above 0 dB")

    lufs = probed.get("loudness_lufs")
    if lufs is not None and float(lufs) < -40:
        silence_risk = True
        notes.append("extremely quiet loudness")

    timestamps = probed.get("timestamps") or {}
    timestamps_available = bool(timestamps.get("words"))

    integrity = 1.0 if exists and readable and not corruption_risk else 0.4
    duration_score = 1.0 if duration_ok else 0.5
    loudness_score = 0.6 if silence_risk or clipping_risk else 0.95
    clarity = 0.95 if timestamps_available else 0.85
    technical_score = round(
        0.35 * integrity
        + 0.25 * duration_score
        + 0.2 * loudness_score
        + 0.1 * clarity
        + 0.1 * (1.0 if sample_rate_ok else 0.5),
        4,
    )
    ok = (
        exists
        and readable
        and duration_ok
        and sample_rate_ok
        and not corruption_risk
        and technical_score >= 0.7
    )
    return TechnicalVoiceQA(
        ok=ok,
        file_exists=exists,
        readable=readable,
        duration_ok=duration_ok,
        sample_rate_ok=sample_rate_ok,
        clipping_risk=clipping_risk,
        silence_risk=silence_risk,
        corruption_risk=corruption_risk,
        timestamps_available=timestamps_available,
        probe_source=source,
        technical_score=technical_score,
        notes=notes,
        probed=probed,
    )


def sha256_file(uri: str) -> tuple[str, int]:
    data = Path(uri).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def script_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
