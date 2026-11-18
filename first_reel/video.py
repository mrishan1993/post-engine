"""Live AI video clips for First Reel — Runway image-to-video (fallback text-to-video)."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from amp_platform.live_videos import available_video_backends, generate_video
from first_reel.live import _SHOT_PROMPTS
from first_reel.spec import SHOTS

_MOTION = (
    "subtle handheld phone-cam motion, slight natural camera drift, "
    "photoreal vertical 9:16, no text overlay, no watermark, no logo"
)


def _shot_duration(shot: dict[str, Any]) -> float:
    return max(0.2, float(shot["t1"]) - float(shot["t0"]))


def _provider_duration(shot_dur: float) -> float:
    # Runway gen4.5 accepts 5 or 10; generate >= shot length then trim in render.
    return 10.0 if shot_dur > 5.0 else 5.0


def _data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _motion_prompt(shot_n: int, label: str) -> str:
    base = _SHOT_PROMPTS.get(shot_n) or f"vertical phone-cam shot labeled {label}"
    return f"{base}. Animate as short video: {_MOTION}."


def generate_live_video_clips(
    out_dir: Path,
    *,
    stills: list[dict[str, Any]] | None = None,
    prefer: str = "runway",
) -> list[dict[str, Any]]:
    """Generate one AI video clip per storyboard shot. Prefers I2V from stills."""
    if not available_video_backends():
        raise RuntimeError(
            "No video API key configured. Set RUNWAY_API_KEY (preferred) or GOOGLE_API_KEY."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    still_by_shot: dict[int, Path] = {}
    for item in stills or []:
        shot_n = int(item.get("shot") or 0)
        frame = Path(str(item.get("frame") or ""))
        if shot_n and frame.exists() and frame.stat().st_size > 1000:
            still_by_shot[shot_n] = frame
    if not still_by_shot:
        for png in sorted(out_dir.glob("shot_*.png")):
            if "card" in png.name:
                continue
            try:
                shot_n = int(png.name.split("_")[1])
            except (IndexError, ValueError):
                continue
            still_by_shot[shot_n] = png

    clips: list[dict[str, Any]] = []
    errors: list[str] = []
    provider_used: str | None = None

    for shot in SHOTS:
        shot_n = int(shot["shot"])
        label = str(shot["label"])
        dest = out_dir / f"shot_{shot_n:02d}_{label.lower()}.mp4"
        card = out_dir / f"shot_{shot_n:02d}_video_card.json"
        prompt = _motion_prompt(shot_n, label)
        shot_dur = _shot_duration(shot)
        gen_dur = _provider_duration(shot_dur)
        used = None
        last_err = None

        if dest.exists() and dest.stat().st_size > 50_000:
            used = "cached_video"
        else:
            still = still_by_shot.get(shot_n)
            image_url = _data_uri(still) if still is not None else None
            try:
                generate_video(
                    prompt,
                    duration_sec=gen_dur,
                    image_url=image_url,
                    out_path=dest,
                    prefer=prefer,
                )
                used = f"{prefer}:{'i2v' if image_url else 't2v'}:gen4.5"
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                if image_url is not None:
                    try:
                        generate_video(
                            prompt,
                            duration_sec=gen_dur,
                            image_url=None,
                            out_path=dest,
                            prefer=prefer,
                        )
                        used = f"{prefer}:t2v_fallback:gen4.5"
                        last_err = None
                    except Exception as exc2:  # noqa: BLE001
                        last_err = f"{last_err} | t2v: {exc2}"

        if used is None or not dest.exists() or dest.stat().st_size < 50_000:
            errors.append(f"shot {shot_n} ({label}): {last_err or 'video generation failed'}")
            continue

        provider_used = used
        meta = {
            **shot,
            "clip": str(dest),
            "frame": str(still_by_shot.get(shot_n) or ""),
            "visual_kind": "live_video",
            "provider": used,
            "prompt": prompt,
            "provider_duration_sec": gen_dur,
            "edit_duration_sec": shot_dur,
            "safe_area": {"top": 180, "bottom": 220, "left": 64, "right": 64},
        }
        card.write_text(json.dumps(meta, indent=2))
        clips.append(
            {
                "shot": shot_n,
                "clip": str(dest),
                "frame": meta["frame"] or str(dest),
                "card": str(card),
                **shot,
                "visual_kind": "live_video",
                "provider": used,
            }
        )
        # Soft pacing to avoid bursts on low-credit accounts
        time.sleep(1.5)

    (out_dir / "video_meta.json").write_text(
        json.dumps(
            {
                "provider": provider_used,
                "errors": errors,
                "shots": len(clips),
                "backends": available_video_backends(),
            },
            indent=2,
        )
    )
    if len(clips) < len(SHOTS):
        missing = sorted({int(s["shot"]) for s in SHOTS} - {int(c["shot"]) for c in clips})
        raise RuntimeError(
            f"AI video incomplete — missing shots {missing}. Errors: {errors}"
        )
    clips.sort(key=lambda c: int(c["shot"]))
    return clips
