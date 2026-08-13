from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from assembly_engine.schemas import AssemblySpecification, BuiltTimeline, TechnicalAssemblyQA


def probe_media(uri: str) -> dict[str, Any]:
    path = Path(uri)
    meta_path = path.with_suffix(".meta.json")
    if shutil.which("ffprobe") and path.exists() and not path.read_bytes()[:20].startswith(b"AMP_"):
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
                timeout=20,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                data = json.loads(proc.stdout)
                video = next(
                    (s for s in data.get("streams") or [] if s.get("codec_type") == "video"),
                    {},
                )
                audio = next(
                    (s for s in data.get("streams") or [] if s.get("codec_type") == "audio"),
                    {},
                )
                return {
                    "source": "ffprobe",
                    "width": int(video.get("width") or 0) or None,
                    "height": int(video.get("height") or 0) or None,
                    "fps": _parse_fps(video.get("r_frame_rate")),
                    "duration_sec": float(
                        video.get("duration") or data.get("format", {}).get("duration") or 0
                    )
                    or None,
                    "video_codec": video.get("codec_name"),
                    "audio_codec": audio.get("codec_name"),
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
            "fps": data.get("fps"),
            "duration_sec": data.get("duration_sec"),
            "video_codec": data.get("video_codec") or "h264",
            "audio_codec": data.get("audio_codec") or "aac",
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


def validate_assembly_spec(spec: AssemblySpecification) -> list[str]:
    issues: list[str] = []
    if spec.duration_sec <= 0:
        issues.append("duration must be positive")
    if not spec.video_clips and not spec.image_clips:
        issues.append("assembly requires at least one video or image clip")
    # Voice must fit inside timeline
    for v in spec.voice_clips:
        if v.end > spec.duration_sec + 0.05:
            issues.append(
                f"voice clip {v.artifact_id} ends after video duration ({v.end}>{spec.duration_sec})"
            )
        if v.start < 0:
            issues.append(f"voice clip {v.artifact_id} has negative start")
    for c in spec.video_clips:
        if c.end <= c.start:
            issues.append(f"video clip {c.artifact_id} has invalid range")
    return issues


def validate_rendered_output(
    uri: str,
    *,
    expected_duration: float,
    expected_width: int = 1080,
    expected_height: int = 1920,
    expected_fps: float = 30.0,
    duration_tolerance: float = 1.5,
) -> TechnicalAssemblyQA:
    path = Path(uri)
    notes: list[str] = []
    exists = path.exists() and path.is_file()
    if not exists:
        return TechnicalAssemblyQA(ok=False, file_exists=False, notes=["file missing"])

    raw = path.read_bytes()
    readable = len(raw) > 0
    if not readable:
        return TechnicalAssemblyQA(ok=False, file_exists=True, readable=False, notes=["empty file"])

    probed = probe_media(uri)
    source = str(probed.get("source") or "none")
    if raw.startswith(b"AMP_ASSEMBLY_STUB"):
        notes.append("stub assembly artifact accepted")

    duration_ok = True
    if probed.get("duration_sec") is not None:
        duration_ok = abs(float(probed["duration_sec"]) - float(expected_duration)) <= duration_tolerance
        if not duration_ok:
            notes.append(
                f"duration mismatch expected={expected_duration} got={probed['duration_sec']}"
            )

    resolution_ok = True
    if probed.get("width") and probed.get("height"):
        resolution_ok = int(probed["width"]) == expected_width and int(probed["height"]) == expected_height
        if not resolution_ok:
            notes.append(
                f"resolution mismatch expected={expected_width}x{expected_height} "
                f"got={probed.get('width')}x{probed.get('height')}"
            )

    fps_ok = True
    if probed.get("fps") is not None:
        fps_ok = abs(float(probed["fps"]) - float(expected_fps)) <= 1.0
        if not fps_ok:
            notes.append(f"fps mismatch expected={expected_fps} got={probed['fps']}")

    codec_ok = True
    if source == "ffprobe":
        if not probed.get("video_codec"):
            codec_ok = False
            notes.append("missing video codec")
        if not probed.get("audio_codec"):
            notes.append("missing audio codec")

    missing_audio = source == "ffprobe" and not probed.get("audio_codec")
    av_sync_ok = duration_ok and not missing_audio

    score = round(
        0.3 * (1.0 if exists and readable else 0)
        + 0.25 * (1.0 if duration_ok else 0.4)
        + 0.2 * (1.0 if resolution_ok else 0.4)
        + 0.15 * (1.0 if fps_ok else 0.5)
        + 0.1 * (1.0 if codec_ok else 0.5),
        4,
    )
    ok = exists and readable and duration_ok and resolution_ok and fps_ok and av_sync_ok and score >= 0.7
    return TechnicalAssemblyQA(
        ok=ok,
        file_exists=exists,
        readable=readable,
        duration_ok=duration_ok,
        resolution_ok=resolution_ok,
        fps_ok=fps_ok,
        codec_ok=codec_ok,
        av_sync_ok=av_sync_ok,
        missing_audio=missing_audio,
        probe_source=source,
        technical_score=score,
        notes=notes,
        probed=probed,
    )


def sha256_file(uri: str) -> tuple[str, int]:
    data = Path(uri).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def collect_source_hashes(timeline: BuiltTimeline) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for track in timeline.tracks:
        for clip in track.clips:
            uri = clip.get("storage_uri")
            aid = clip.get("artifact_id")
            if uri and Path(uri).exists() and aid:
                digest, _ = sha256_file(uri)
                hashes[str(aid)] = digest
    return hashes
