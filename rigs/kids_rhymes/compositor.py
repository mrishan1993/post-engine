from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _write_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    """Minimal solid-color PNG writer (no Pillow dependency)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    r, g, b = rgb
    raw = b"".join(b"\x00" + bytes([r, g, b]) * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def render(audio_path: str, audio_duration_sec: int, output_dir: str) -> str:
    """Phase-1 minimal rig: static colorful frame placeholder.

    Later: mouth-flap sync driven by audio amplitude using character_parts/.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "visual.png"
    # Bright kids-friendly blue frame at vertical Shorts aspect (scaled down for stubs)
    _write_png(path, 540, 960, (70, 160, 255))

    # Ensure character_parts exist as placeholders for the full rig.
    parts = Path(__file__).parent / "character_parts"
    parts.mkdir(parents=True, exist_ok=True)
    for name, color in (
        ("body.png", (255, 200, 80)),
        ("mouth_closed.png", (200, 80, 80)),
        ("mouth_open.png", (220, 60, 60)),
    ):
        part_path = parts / name
        if not part_path.exists():
            _write_png(part_path, 128, 128, color)

    bg_dir = Path(__file__).parent / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    bg = bg_dir / "default.png"
    if not bg.exists():
        _write_png(bg, 540, 960, (180, 230, 255))

    _ = (audio_path, audio_duration_sec)  # reserved for amplitude-driven mouth flaps
    return str(path)
