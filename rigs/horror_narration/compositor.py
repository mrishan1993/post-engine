from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _write_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
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
    """Phase-1: dark static still. Later: Ken Burns pan/zoom timed to narration."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "visual.png"
    _write_png(path, 540, 960, (20, 18, 28))

    bg_dir = Path(__file__).parent / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    bg = bg_dir / "default.png"
    if not bg.exists():
        _write_png(bg, 540, 960, (12, 10, 16))

    _ = (audio_path, audio_duration_sec)
    return str(path)
