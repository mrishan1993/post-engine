"""FFmpeg render for First Reel #1 — silent 9:16 master (audio attaches at publish)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from amp_platform.procedural_media import resolve_ffmpeg
from config.settings import get_settings
from first_reel.spec import SHOTS

_WIDTH = 1080
_HEIGHT = 1920
_FPS = 30
_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"


def _escape_drawtext(text: str) -> str:
    cleaned = (
        text.replace("😭", "")
        .replace("❤️", "<3")
        .replace("\n", " ")
        .strip()
    )
    return (
        cleaned.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _fontfile() -> str:
    for candidate in (
        _FONT,
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if Path(candidate).is_file():
            return candidate
    return _FONT


def _shot_duration(shot: dict[str, Any]) -> float:
    return max(0.2, float(shot["t1"]) - float(shot["t0"]))


def _text_style(shot: dict[str, Any]) -> tuple[int, str]:
    """Return (fontsize, y_expression)."""
    label = shot.get("label")
    if label == "UNLOCK":
        return 160, "(h-text_h)/2"
    if label in {"HOOK", "LOOP"}:
        return 64, "h*0.62"
    if label == "PUNCHLINE":
        return 72, "(h-text_h)/2"
    if label == "STATUS":
        return 52, "h*0.52"
    if label == "SELFIE":
        return 48, "h*0.78"
    return 48, "h*0.75"


def _motion_vf(shot: dict[str, Any], duration: float) -> str:
    """Hard-cut friendly motion — avoid heavy zoompan (too slow for 1080×1920)."""
    _ = duration
    label = shot.get("label")
    parts = [
        f"scale={_WIDTH}:{_HEIGHT}:force_original_aspect_ratio=increase",
        f"crop={_WIDTH}:{_HEIGHT}",
        f"fps={_FPS}",
        "format=yuv420p",
    ]
    # Subtle push-in via scale+crop offset (cheap)
    if label in {"HOOK", "UNLOCK", "LOOP", "SELFIE"}:
        parts = [
            f"scale={int(_WIDTH * 1.06)}:{int(_HEIGHT * 1.06)}",
            f"crop={_WIDTH}:{_HEIGHT}",
            f"fps={_FPS}",
            "format=yuv420p",
        ]
    text = shot.get("text")
    if text:
        escaped = _escape_drawtext(str(text))
        size, y_expr = _text_style(shot)
        parts.append(
            f"drawtext=fontfile={_fontfile()}:text='{escaped}':fontsize={size}:"
            f"fontcolor=white:borderw=3:bordercolor=black@0.75:box=1:boxcolor=black@0.4:"
            f"boxborderw=22:x=(w-text_w)/2:y={y_expr}"
        )
    if label == "SELFIE":
        parts.append("fade=t=in:st=0:d=0.12:color=white")
    return ",".join(parts)


def _render_shot_clip(
    *,
    ffmpeg: str,
    frame: Path,
    shot: dict[str, Any],
    out_path: Path,
) -> None:
    duration = _shot_duration(shot)
    vf = _motion_vf(shot, duration)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-loop",
        "1",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(frame),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(_FPS),
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(proc.stderr[-2000:] if proc.stderr else "ffmpeg shot render failed")


def render_package_dir(
    package_dir: Path,
    *,
    out_name: str = "first_reel_2016_phone.mp4",
    regenerate_plates: bool | None = None,
) -> dict[str, Any]:
    """Render a silent 9:16 MP4 from an existing first-reel package directory."""
    package_dir = Path(package_dir)
    pkg_path = package_dir / "reel_package.json"
    if not pkg_path.exists():
        raise FileNotFoundError(f"missing package: {pkg_path}")

    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found — place a binary at storage/bin/ffmpeg or install ffmpeg on PATH"
        )

    package = json.loads(pkg_path.read_text())
    frames_meta = package.get("frames") or []
    shots = package.get("spec", {}).get("shots") or SHOTS
    visual_kind = str(package.get("visual_kind") or "")
    if not visual_kind and frames_meta:
        visual_kind = str(frames_meta[0].get("visual_kind") or "")

    # Upgrade old solid-color packages in place, but never overwrite live API stills.
    if regenerate_plates is None:
        regenerate_plates = visual_kind not in {"live_api", "replicate", "fal", "openai", "gemini"}
    if regenerate_plates:
        from first_reel.plates import write_shot_frames

        frames_meta = write_shot_frames(package_dir / "frames")
        package["frames"] = frames_meta
        visual_kind = "procedural_phone_cam"
        package["visual_kind"] = visual_kind

    frame_by_shot: dict[int, Path] = {}
    for item in frames_meta:
        frame_by_shot[int(item["shot"])] = Path(item["frame"])

    out_path = package_dir / out_name
    with tempfile.TemporaryDirectory(prefix="first_reel_render_") as tmp:
        tmp_path = Path(tmp)
        concat_lines: list[str] = []
        for shot in shots:
            shot_n = int(shot["shot"])
            frame = frame_by_shot.get(shot_n)
            if frame is None or not frame.exists():
                candidates = sorted((package_dir / "frames").glob(f"shot_{shot_n:02d}_*.png"))
                candidates = [p for p in candidates if "card" not in p.name]
                if not candidates:
                    raise FileNotFoundError(f"missing frame for shot {shot_n}")
                frame = candidates[0]
            clip = tmp_path / f"shot_{shot_n:02d}.mp4"
            _render_shot_clip(ffmpeg=ffmpeg, frame=frame, shot=shot, out_path=clip)
            safe = str(clip).replace("'", "'\\''")
            concat_lines.append(f"file '{safe}'")

        list_file = tmp_path / "concat.txt"
        list_file.write_text("\n".join(concat_lines) + "\n")
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
        if proc.returncode != 0 or not out_path.exists():
            raise RuntimeError(proc.stderr[-2000:] if proc.stderr else "ffmpeg concat failed")

    duration = sum(_shot_duration(s) for s in shots)
    render_info = {
        "render_uri": str(out_path),
        "width": _WIDTH,
        "height": _HEIGHT,
        "fps": _FPS,
        "duration_sec": duration,
        "audio": None,
        "audio_strategy": "platform_native",
        "ffmpeg": ffmpeg,
        "ffmpeg_used": True,
        "silent_master": True,
        "visual_kind": visual_kind or "procedural_phone_cam",
        "note": "Silent master — attach trending platform-native audio at Instagram publish.",
    }
    package["render"] = render_info
    package["visual_kind"] = visual_kind or "procedural_phone_cam"
    if visual_kind == "live_api":
        package["note"] = (
            "Rendered silent 9:16 reel from live API stills + motion. "
            "Native trend audio attaches at publish."
        )
    else:
        package["note"] = (
            "Rendered silent 9:16 phone-cam reel (procedural plates + motion). "
            "Native trend audio attaches at publish."
        )
    pkg_path.write_text(json.dumps(package, indent=2, default=str))
    (package_dir / "render.json").write_text(json.dumps(render_info, indent=2))
    return render_info


def render_content_id(content_id: str) -> dict[str, Any]:
    root = Path(get_settings().storage_root) / "first_reel" / content_id
    return render_package_dir(root)


def latest_package_dir() -> Path | None:
    root = Path(get_settings().storage_root) / "first_reel"
    if not root.exists():
        return None
    dirs = sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / "reel_package.json").exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return dirs[0] if dirs else None
