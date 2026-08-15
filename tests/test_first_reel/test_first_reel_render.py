from __future__ import annotations

from pathlib import Path

from first_reel.package import write_reel_package
from first_reel.render import resolve_ffmpeg, render_package_dir


def test_resolve_ffmpeg_or_skip() -> None:
    # Bundled or PATH — either is fine; render test below gates on presence
    path = resolve_ffmpeg()
    assert path is None or Path(path).exists()


def test_render_first_reel_mp4(tmp_path: Path) -> None:
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        return  # environment without ffmpeg — package still ships frames
    pkg = write_reel_package(
        tmp_path / "pkg",
        lineage={"content_id": "content_test"},
        job={"job_id": "job_test", "status": "LEARNING"},
    )
    # Plates must not be flat solid fills
    frames_dir = Path(pkg["frames_dir"])
    sample = next(frames_dir.glob("shot_01_*.png"))
    data = sample.read_bytes()
    assert data.startswith(b"\x89PNG")
    assert sample.stat().st_size > 5_000

    info = render_package_dir(Path(pkg["package_path"]).parent)
    out = Path(info["render_uri"])
    assert out.exists()
    assert out.stat().st_size > 50_000
    assert info["width"] == 1080
    assert info["height"] == 1920
    assert info["silent_master"] is True
    assert abs(info["duration_sec"] - 13.0) < 0.01
    assert info.get("visual_kind") == "procedural_phone_cam"
