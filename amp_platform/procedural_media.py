"""Procedural media — real PNG/MP4 placeholders (no paid APIs, no AMP_* fake files)."""

from __future__ import annotations

import hashlib
import math
import random
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from typing import Iterable


def resolve_ffmpeg() -> str | None:
    which = shutil.which("ffmpeg")
    if which:
        return which
    for candidate in (
        Path(__file__).resolve().parents[1] / "storage" / "bin" / "ffmpeg",
        Path("storage/bin/ffmpeg"),
    ):
        if candidate.is_file():
            return str(candidate)
    try:
        from config.settings import get_settings

        bundled = Path(get_settings().storage_root) / "bin" / "ffmpeg"
        if bundled.is_file():
            return str(bundled)
    except Exception:  # noqa: BLE001
        pass
    return None


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    """Write 8-bit RGB PNG. `rgb` length must be width*height*3."""
    if len(rgb) != width * height * 3:
        raise ValueError("rgb buffer size mismatch")
    raw = bytearray()
    row = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(rgb[y * row : (y + 1) * row])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += _png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


class Canvas:
    """Minimal RGB canvas for phone-cam plates."""

    __slots__ = ("w", "h", "buf")

    def __init__(self, width: int, height: int, rgb: tuple[int, int, int] = (0, 0, 0)):
        self.w = width
        self.h = height
        r, g, b = rgb
        self.buf = bytearray([r, g, b] * (width * height))

    def _i(self, x: int, y: int) -> int:
        return (y * self.w + x) * 3

    def set(self, x: int, y: int, rgb: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = self._i(x, y)
            self.buf[i], self.buf[i + 1], self.buf[i + 2] = rgb

    def get(self, x: int, y: int) -> tuple[int, int, int]:
        i = self._i(x, y)
        return self.buf[i], self.buf[i + 1], self.buf[i + 2]

    def fill(self, rgb: tuple[int, int, int]) -> None:
        r, g, b = rgb
        self.buf[:] = bytes([r, g, b]) * (self.w * self.h)

    def gradient_v(self, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
        for y in range(self.h):
            t = y / max(1, self.h - 1)
            rgb = bytes(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
            start = y * self.w * 3
            self.buf[start : start + self.w * 3] = rgb * self.w

    def gradient_h(self, left: tuple[int, int, int], right: tuple[int, int, int]) -> None:
        for x in range(self.w):
            t = x / max(1, self.w - 1)
            rgb = tuple(int(left[i] * (1 - t) + right[i] * t) for i in range(3))
            for y in range(self.h):
                self.set(x, y, rgb)  # type: ignore[arg-type]

    def rect(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        rgb: tuple[int, int, int],
        *,
        fill: bool = True,
        thickness: int = 2,
    ) -> None:
        x0, x1 = max(0, min(x0, x1)), min(self.w, max(x0, x1))
        y0, y1 = max(0, min(y0, y1)), min(self.h, max(y0, y1))
        if fill:
            row = bytes(rgb)
            for y in range(y0, y1):
                start = self._i(x0, y)
                end = self._i(x1, y)
                self.buf[start:end] = row * (x1 - x0)
        else:
            self.rect(x0, y0, x1, y0 + thickness, rgb, fill=True)
            self.rect(x0, y1 - thickness, x1, y1, rgb, fill=True)
            self.rect(x0, y0, x0 + thickness, y1, rgb, fill=True)
            self.rect(x1 - thickness, y0, x1, y1, rgb, fill=True)

    def round_rect(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        radius: int,
        rgb: tuple[int, int, int],
    ) -> None:
        self.rect(x0 + radius, y0, x1 - radius, y1, rgb)
        self.rect(x0, y0 + radius, x1, y1 - radius, rgb)
        for cx, cy in (
            (x0 + radius, y0 + radius),
            (x1 - radius - 1, y0 + radius),
            (x0 + radius, y1 - radius - 1),
            (x1 - radius - 1, y1 - radius - 1),
        ):
            self.ellipse(cx, cy, radius, radius, rgb)

    def ellipse(
        self,
        cx: int,
        cy: int,
        rx: int,
        ry: int,
        rgb: tuple[int, int, int],
        *,
        fill: bool = True,
    ) -> None:
        rx = max(1, rx)
        ry = max(1, ry)
        for y in range(cy - ry, cy + ry + 1):
            if y < 0 or y >= self.h:
                continue
            dy = (y - cy) / ry
            span = int(rx * math.sqrt(max(0.0, 1.0 - dy * dy)))
            if fill:
                self.rect(cx - span, y, cx + span + 1, y + 1, rgb)
            else:
                self.set(cx - span, y, rgb)
                self.set(cx + span, y, rgb)

    def blend_ellipse(
        self,
        cx: int,
        cy: int,
        rx: int,
        ry: int,
        rgb: tuple[int, int, int],
        alpha: float,
    ) -> None:
        a = max(0.0, min(1.0, alpha))
        for y in range(max(0, cy - ry), min(self.h, cy + ry + 1)):
            dy = (y - cy) / max(1, ry)
            span = int(rx * math.sqrt(max(0.0, 1.0 - dy * dy)))
            for x in range(max(0, cx - span), min(self.w, cx + span + 1)):
                r0, g0, b0 = self.get(x, y)
                self.set(
                    x,
                    y,
                    (
                        int(r0 * (1 - a) + rgb[0] * a),
                        int(g0 * (1 - a) + rgb[1] * a),
                        int(b0 * (1 - a) + rgb[2] * a),
                    ),
                )

    def noise(self, amount: int, seed: int = 0) -> None:
        """Sparse grain (every 3rd pixel) — fast enough for 1080×1920 plates."""
        rng = random.Random(seed)
        step = 9  # 3 pixels * 3 channels
        for i in range(0, len(self.buf) - 2, step):
            d = rng.randint(-amount, amount)
            self.buf[i] = max(0, min(255, self.buf[i] + d))
            self.buf[i + 1] = max(0, min(255, self.buf[i + 1] + d))
            self.buf[i + 2] = max(0, min(255, self.buf[i + 2] + d))

    def vignette(self, strength: float = 0.45) -> None:
        """Edge darkening via border bands (avoids O(w*h) python loops)."""
        bands = 28
        for i in range(bands):
            a = strength * ((i + 1) / bands) * 0.55
            shade = (0, 0, 0)
            # Approximate alpha darken by blending toward black on borders
            self._blend_border(i, shade, a)

    def _blend_border(self, inset: int, rgb: tuple[int, int, int], alpha: float) -> None:
        a = max(0.0, min(1.0, alpha))
        if inset >= self.w // 2 or inset >= self.h // 2:
            return
        for y in (inset, self.h - 1 - inset):
            if 0 <= y < self.h:
                for x in range(inset, self.w - inset):
                    r0, g0, b0 = self.get(x, y)
                    self.set(
                        x,
                        y,
                        (
                            int(r0 * (1 - a) + rgb[0] * a),
                            int(g0 * (1 - a) + rgb[1] * a),
                            int(b0 * (1 - a) + rgb[2] * a),
                        ),
                    )
        for x in (inset, self.w - 1 - inset):
            if 0 <= x < self.w:
                for y in range(inset, self.h - inset):
                    r0, g0, b0 = self.get(x, y)
                    self.set(
                        x,
                        y,
                        (
                            int(r0 * (1 - a) + rgb[0] * a),
                            int(g0 * (1 - a) + rgb[1] * a),
                            int(b0 * (1 - a) + rgb[2] * a),
                        ),
                    )

    def save(self, path: Path) -> None:
        write_png(path, self.w, self.h, bytes(self.buf))


def _seed_color(seed: str, i: int = 0) -> tuple[int, int, int]:
    h = hashlib.md5(f"{seed}:{i}".encode()).hexdigest()
    return (40 + int(h[0:2], 16) % 180, 40 + int(h[2:4], 16) % 180, 40 + int(h[4:6], 16) % 180)


def compose_generic_plate(
    path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    prompt: str = "",
    seed: int | None = None,
) -> Path:
    """Non-uniform prompt-tinted plate (used by generation stubs)."""
    s = seed if seed is not None else int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)
    c = Canvas(width, height)
    top = _seed_color(str(s), 0)
    bot = _seed_color(str(s), 1)
    c.gradient_v(top, bot)
    # Abstract subject blob
    c.blend_ellipse(width // 2, int(height * 0.42), width // 3, height // 5, (240, 230, 210), 0.55)
    c.blend_ellipse(width // 2, int(height * 0.38), width // 8, height // 14, (60, 50, 45), 0.35)
    # Frame chrome
    margin = 48
    c.rect(margin, margin, width - margin, height - margin, (20, 20, 24), fill=False, thickness=10)
    c.noise(12, seed=s)
    c.vignette(0.35)
    path = Path(path)
    c.save(path)
    return path


def compose_phone_bezel(c: Canvas, *, screen: tuple[int, int, int]) -> tuple[int, int, int, int]:
    """Draw phone body; return screen rect (x0,y0,x1,y1)."""
    w, h = c.w, c.h
    x0, y0, x1, y1 = int(w * 0.12), int(h * 0.08), int(w * 0.88), int(h * 0.92)
    c.round_rect(x0, y0, x1, y1, 48, (18, 18, 22))
    inset = 18
    sx0, sy0, sx1, sy1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    c.round_rect(sx0, sy0, sx1, sy1, 36, screen)
    # Notch / speaker
    c.round_rect(w // 2 - 70, sy0 + 18, w // 2 + 70, sy0 + 36, 8, (10, 10, 12))
    return sx0, sy0, sx1, sy1


def compose_shot_plate(
    path: Path,
    *,
    label: str,
    width: int = 1080,
    height: int = 1920,
    seed: int = 2016,
) -> Path:
    """2016-phone POV plates — readable as a reel beat without generative APIs."""
    c = Canvas(width, height)
    label = (label or "").upper()

    if label in {"HOOK", "LOOP"}:
        c.gradient_v((12, 12, 16), (4, 4, 8))
        # Desk / hand context
        c.rect(0, int(height * 0.78), width, height, (55, 42, 32))
        c.blend_ellipse(width // 2, int(height * 0.82), 420, 120, (70, 50, 40), 0.4)
        sx0, sy0, sx1, sy1 = compose_phone_bezel(c, screen=(28, 36, 58))
        # Wallpaper stripes (old iOS feel)
        for i in range(0, sy1 - sy0, 28):
            shade = 40 + (i // 28) % 3 * 12
            c.rect(sx0, sy0 + 50 + i, sx1, sy0 + 50 + i + 14, (shade, shade + 15, shade + 35))
        # Clock blocks (stand-in digits)
        cx = width // 2
        cy = int(height * 0.30)
        for dx in (-140, -40, 40, 140):
            c.round_rect(cx + dx - 28, cy - 50, cx + dx + 28, cy + 50, 8, (245, 245, 250))
        c.round_rect(cx - 12, cy - 12, cx + 12, cy + 12, 4, (245, 245, 250))  # colon
        # Date pill
        c.round_rect(cx - 120, cy + 80, cx + 120, cy + 120, 14, (255, 255, 255))
        # Camera / flash glint on bezel
        c.ellipse(sx1 - 40, sy0 + 40, 10, 10, (200, 200, 210))
        c.noise(10, seed=seed)
        c.vignette(0.35)

    elif label == "UNLOCK":
        c.gradient_v((20, 40, 32), (12, 24, 20))
        sx0, sy0, sx1, sy1 = compose_phone_bezel(c, screen=(48, 96, 72))
        # Status bar
        c.rect(sx0, sy0 + 40, sx1, sy0 + 70, (30, 60, 45))
        for i in range(4):
            c.rect(sx1 - 90 + i * 14, sy0 + 48, sx1 - 82 + i * 14, sy0 + 62, (200, 230, 200))
        # Huge year card
        c.round_rect(sx0 + 60, int(height * 0.26), sx1 - 60, int(height * 0.48), 24, (24, 48, 36))
        # Fake digit bars for "2016"
        y = int(height * 0.32)
        for dx, wbar in ((-220, 70), (-110, 70), (0, 70), (110, 70)):
            c.round_rect(width // 2 + dx, y, width // 2 + dx + wbar, y + 160, 10, (230, 245, 230))
        # Slide to unlock
        c.round_rect(sx0 + 50, sy1 - 170, sx1 - 50, sy1 - 100, 28, (80, 130, 95))
        c.round_rect(sx0 + 58, sy1 - 162, sx0 + 180, sy1 - 108, 24, (235, 245, 235))
        c.rect(sx0 + 200, sy1 - 145, sx1 - 80, sy1 - 125, (180, 210, 185))
        c.noise(8, seed=seed + 1)

    elif label == "SELFIE":
        # Bathroom/mirror wash
        c.gradient_v((190, 150, 130), (120, 80, 70))
        c.rect(0, 0, width, 120, (210, 200, 190))
        # Flash
        c.blend_ellipse(width - 100, 160, 220, 220, (255, 255, 250), 0.9)
        # Shoulders
        c.ellipse(width // 2, int(height * 0.78), 340, 160, (90, 70, 120))
        # Face
        c.ellipse(width // 2, int(height * 0.42), 270, 350, (235, 195, 165))
        # Bangs / hair
        c.ellipse(width // 2, int(height * 0.26), 300, 140, (35, 25, 20))
        c.ellipse(width // 2 - 160, int(height * 0.40), 70, 160, (35, 25, 20))
        c.ellipse(width // 2 + 160, int(height * 0.40), 70, 160, (35, 25, 20))
        # Eyes + catchlights
        c.ellipse(width // 2 - 85, int(height * 0.38), 32, 20, (40, 30, 25))
        c.ellipse(width // 2 + 85, int(height * 0.38), 32, 20, (40, 30, 25))
        c.ellipse(width // 2 - 78, int(height * 0.37), 8, 8, (240, 240, 240))
        c.ellipse(width // 2 + 92, int(height * 0.37), 8, 8, (240, 240, 240))
        # Nose / mouth
        c.ellipse(width // 2, int(height * 0.45), 18, 28, (210, 160, 140))
        c.ellipse(width // 2, int(height * 0.52), 55, 22, (200, 110, 110))
        # Snapchat-ish dog filter ears + nose
        c.ellipse(width // 2 - 200, int(height * 0.22), 55, 80, (255, 200, 80))
        c.ellipse(width // 2 + 200, int(height * 0.22), 55, 80, (255, 200, 80))
        c.ellipse(width // 2, int(height * 0.48), 40, 32, (40, 30, 30))
        # Timestamp stamp
        c.round_rect(60, height - 220, 320, height - 170, 10, (0, 0, 0))
        c.noise(20, seed=seed + 2)
        c.vignette(0.3)

    elif label == "STATUS":
        c.gradient_v((55, 75, 105), (30, 42, 65))
        # iMessage-ish chrome
        c.rect(0, 0, width, 180, (240, 240, 245))
        c.rect(0, 140, width, 180, (220, 220, 230))
        c.ellipse(90, 90, 36, 36, (180, 190, 210))  # avatar
        c.round_rect(150, 70, 420, 110, 8, (60, 60, 70))  # name bar
        c.rect(0, height - 160, width, height, (240, 240, 245))
        c.round_rect(40, height - 120, width - 160, height - 60, 24, (255, 255, 255))
        # Older received bubbles
        c.round_rect(80, 240, 520, 320, 22, (225, 225, 235))
        c.round_rect(80, 360, 600, 440, 22, (225, 225, 235))
        # Main status bubble
        bx0, by0 = int(width * 0.14), int(height * 0.48)
        bx1, by1 = int(width * 0.90), int(height * 0.62)
        c.round_rect(bx0, by0, bx1, by1, 28, (50, 150, 255))
        c.ellipse(bx0 + 36, by1 - 8, 28, 22, (50, 150, 255))
        # Heart reaction
        c.ellipse(bx1 - 70, by0 - 30, 28, 24, (230, 60, 90))
        c.ellipse(bx1 - 50, by0 - 30, 28, 24, (230, 60, 90))
        c.noise(5, seed=seed + 3)

    elif label == "MONTAGE":
        c.fill((10, 10, 14))
        panels = [
            ((24, 24, width // 2 - 12, height // 2 - 12), (28, 30, 48), "music"),
            ((width // 2 + 12, 24, width - 24, height // 2 - 12), (48, 36, 52), "snap"),
            ((24, height // 2 + 12, width // 2 - 12, height - 24), (32, 40, 34), "wires"),
            ((width // 2 + 12, height // 2 + 12, width - 24, height - 24), (42, 36, 32), "ig"),
        ]
        for (x0, y0, x1, y1), color, kind in panels:
            c.round_rect(x0, y0, x1, y1, 18, color)
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            if kind == "music":
                c.round_rect(cx - 140, cy - 140, cx + 140, cy + 40, 16, (20, 22, 30))
                for i in range(6):
                    bh = 50 + (i * 37) % 140
                    c.rect(cx - 100 + i * 36, cy + 80 - bh, cx - 80 + i * 36, cy + 80, (90, 220, 160))
                c.ellipse(cx, cy - 50, 50, 50, (255, 80, 120))
            elif kind == "snap":
                c.ellipse(cx, cy - 20, 120, 140, (255, 230, 90))
                c.ellipse(cx, cy - 20, 95, 115, (40, 30, 30))
                c.ellipse(cx - 35, cy - 40, 16, 16, (255, 255, 255))
                c.ellipse(cx + 35, cy - 40, 16, 16, (255, 255, 255))
                c.round_rect(cx - 80, cy + 120, cx + 80, cy + 160, 10, (255, 230, 90))
            elif kind == "wires":
                c.ellipse(cx, cy - 100, 70, 70, (25, 25, 30))
                c.rect(cx - 10, cy - 40, cx + 10, cy + 100, (210, 210, 220))
                c.ellipse(cx - 50, cy + 110, 40, 50, (30, 30, 35))
                c.ellipse(cx + 50, cy + 110, 40, 50, (30, 30, 35))
            else:
                # Old IG profile chrome
                c.round_rect(cx - 150, cy - 160, cx + 150, cy + 160, 12, (250, 250, 252))
                c.ellipse(cx, cy - 70, 55, 55, (220, 120, 100))
                c.round_rect(cx - 90, cy + 10, cx + 90, cy + 40, 6, (40, 40, 45))
                c.round_rect(cx - 120, cy + 60, cx - 20, cy + 120, 6, (230, 230, 235))
                c.round_rect(cx + 10, cy + 60, cx + 110, cy + 120, 6, (230, 230, 235))
        c.noise(10, seed=seed + 4)

    elif label == "PUNCHLINE":
        c.fill((4, 4, 6))
        # Faint phone ghost for continuity
        c.blend_ellipse(width // 2, int(height * 0.45), 200, 360, (25, 25, 30), 0.35)
        c.noise(3, seed=seed + 5)

    else:
        compose_generic_plate(path, width=width, height=height, prompt=label, seed=seed)
        return Path(path)

    path = Path(path)
    c.save(path)
    return path


def materialize_png(
    path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    prompt: str = "",
    seed: int | None = None,
    label: str | None = None,
) -> Path:
    if label:
        return compose_shot_plate(path, label=label, width=width, height=height, seed=seed or 0)
    return compose_generic_plate(path, width=width, height=height, prompt=prompt, seed=seed)


def materialize_mp4(
    path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    duration_sec: float = 2.0,
    prompt: str = "",
    seed: int | None = None,
    label: str | None = None,
    text: str | None = None,
) -> Path:
    """Write a real H.264 MP4 (silent) from a procedural plate + mild motion."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_ffmpeg()
    still = path.with_suffix(".plate.png")
    materialize_png(still, width=width, height=height, prompt=prompt, seed=seed, label=label)

    if not ffmpeg:
        # No encoder — leave a real PNG and copy bytes with .mp4 name is wrong;
        # write minimal motion-less by requiring ffmpeg for video.
        raise RuntimeError("ffmpeg required to materialize real mp4")

    overlay = text or (prompt.strip().split("\n")[0][:48] if prompt else "")
    overlay = (
        overlay.replace("😭", "")
        .replace("❤️", "<3")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )
    # Lightweight motion (no heavy zoompan)
    vf = f"scale={width}:{height},fps=30,format=yuv420p"
    font = "/System/Library/Fonts/Supplemental/Arial.ttf"
    if overlay and Path(font).is_file():
        vf += (
            f",drawtext=fontfile={font}:text='{overlay}':fontsize=54:fontcolor=white:"
            f"borderw=3:bordercolor=black@0.7:box=1:boxcolor=black@0.35:boxborderw=18:"
            f"x=(w-text_w)/2:y=h*0.72"
        )

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-loop",
        "1",
        "-t",
        f"{float(duration_sec):.3f}",
        "-i",
        str(still),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0 or not path.exists() or path.stat().st_size < 1000:
        raise RuntimeError(proc.stderr[-1500:] if proc.stderr else "ffmpeg materialize failed")
    return path


def infer_shot_label(prompt: str) -> str | None:
    p = (prompt or "").lower()
    for label, keys in (
        ("HOOK", ("pov", "find your", "2016 phone", "hook")),
        ("UNLOCK", ("unlock", "lock screen", "2016")),
        ("SELFIE", ("selfie", "flash", "dress like")),
        ("STATUS", ("status", "life is good", "message")),
        ("MONTAGE", ("montage", "snapchat", "earphones", "music player")),
        ("PUNCHLINE", ("punchline", "happier", "payoff")),
        ("LOOP", ("loop", "return to phone")),
    ):
        if any(k in p for k in keys):
            return label
    return None
