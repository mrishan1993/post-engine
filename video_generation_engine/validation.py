from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from video_generation_engine.schemas import TechnicalVideoQA


def _parse_aspect(ratio: str) -> float | None:
    try:
        a, b = ratio.split(":")
        return float(a) / float(b)
    except Exception:  # noqa: BLE001
        return None


def probe_video(uri: str) -> dict[str, Any]:
    """Prefer ffprobe; fall back to stub sidecar metadata."""
    path = Path(uri)
    meta_path = path.with_suffix(".meta.json")
    if shutil.which("ffprobe"):
        try:
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                data = json.loads(proc.stdout)
                video = next(
                    (s for s in data.get("streams") or [] if s.get("codec_type") == "video"),
                    {},
                )
                return {
                    "source": "ffprobe",
                    "width": int(video.get("width") or 0) or None,
                    "height": int(video.get("height") or 0) or None,
                    "duration_sec": float(
                        video.get("duration") or data.get("format", {}).get("duration") or 0
                    )
                    or None,
                    "fps": _parse_fps(video.get("r_frame_rate")),
                    "codec": video.get("codec_name"),
                    "size_bytes": int(data.get("format", {}).get("size") or path.stat().st_size),
                }
        except Exception:  # noqa: BLE001
            pass

    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return {
            "source": "stub",
            "width": data.get("width"),
            "height": data.get("height"),
            "duration_sec": data.get("duration_sec"),
            "fps": data.get("fps"),
            "codec": "stub",
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
    return {"source": "none", "size_bytes": path.stat().st_size if path.exists() else 0}


def _parse_fps(rate: str | None) -> float | None:
    if not rate or rate == "0/0":
        return None
    if "/" in rate:
        a, b = rate.split("/")
        try:
            return round(float(a) / float(b), 3)
        except Exception:  # noqa: BLE001
            return None
    try:
        return float(rate)
    except Exception:  # noqa: BLE001
        return None


def validate_video_artifact(
    uri: str,
    *,
    expected_duration: float | None = None,
    expected_aspect: str | None = None,
    expected_resolution: str | None = None,
    expected_fps: float | None = None,
    duration_tolerance: float = 0.75,
) -> TechnicalVideoQA:
    path = Path(uri)
    notes: list[str] = []
    exists = path.exists() and path.is_file()
    if not exists:
        return TechnicalVideoQA(ok=False, file_exists=False, notes=["file missing"])

    raw = path.read_bytes()
    readable = len(raw) > 0
    if not readable:
        return TechnicalVideoQA(ok=False, file_exists=True, readable=False, notes=["empty file"])

    probed = probe_video(uri)
    source = str(probed.get("source") or "none")

    # Stub marker sanity
    black_risk = False
    frozen_risk = False
    if raw.startswith(b"AMP_VIDEO_STUB"):
        notes.append("stub artifact accepted")
    elif source == "none":
        notes.append("no probe metadata; basic checks only")

    duration_ok = True
    if expected_duration is not None and probed.get("duration_sec") is not None:
        duration_ok = abs(float(probed["duration_sec"]) - float(expected_duration)) <= duration_tolerance
        if not duration_ok:
            notes.append(
                f"duration mismatch expected={expected_duration} got={probed['duration_sec']}"
            )

    dimensions_ok = True
    exp_w = exp_h = None
    if expected_resolution and "x" in expected_resolution:
        try:
            exp_w, exp_h = [int(x) for x in expected_resolution.lower().split("x")[:2]]
        except ValueError:
            exp_w = exp_h = None
    if exp_w and exp_h and probed.get("width") and probed.get("height"):
        dimensions_ok = int(probed["width"]) == exp_w and int(probed["height"]) == exp_h
        if not dimensions_ok:
            notes.append(
                f"resolution mismatch expected={expected_resolution} "
                f"got={probed.get('width')}x{probed.get('height')}"
            )

    aspect_ok = True
    if expected_aspect and probed.get("width") and probed.get("height"):
        target = _parse_aspect(expected_aspect)
        if target:
            actual = float(probed["width"]) / float(probed["height"])
            aspect_ok = abs(actual - target) < 0.05
            if not aspect_ok:
                notes.append(f"aspect mismatch expected={expected_aspect} got={actual:.3f}")

    fps_ok = True
    if expected_fps is not None and probed.get("fps") is not None:
        fps_ok = abs(float(probed["fps"]) - float(expected_fps)) <= 1.0
        if not fps_ok:
            notes.append(f"fps mismatch expected={expected_fps} got={probed['fps']}")

    codec_ok = True
    if source == "ffprobe" and not probed.get("codec"):
        codec_ok = False
        notes.append("missing video codec")

    ok = exists and readable and duration_ok and dimensions_ok and aspect_ok and fps_ok and codec_ok
    return TechnicalVideoQA(
        ok=ok,
        file_exists=exists,
        readable=readable,
        codec_ok=codec_ok,
        duration_ok=duration_ok,
        dimensions_ok=dimensions_ok,
        aspect_ratio_ok=aspect_ok,
        fps_ok=fps_ok,
        black_frame_risk=black_risk,
        frozen_frame_risk=frozen_risk,
        probe_source=source,
        notes=notes,
        probed=probed,
    )


def sha256_file(uri: str) -> tuple[str, int]:
    data = Path(uri).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)
