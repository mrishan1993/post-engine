"""Shot frame writer for First Reel — procedural/live stills, optional AI video."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from amp_platform.procedural_media import compose_shot_plate
from first_reel.spec import SHOTS


def write_shot_frames(
    out_dir: Path,
    *,
    live: bool = False,
    video: bool = False,
    prefer_video: str = "runway",
) -> list[dict[str, Any]]:
    """Write one PNG per shot; when video=True, also generate AI clips (Runway/Veo)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    if live:
        from first_reel.live import generate_live_frames

        try:
            frames = generate_live_frames(out_dir)
        except Exception:  # noqa: BLE001
            frames = []

    if not frames or len(frames) < len(SHOTS):
        frames = []
        for shot in SHOTS:
            label = str(shot["label"])
            path = out_dir / f"shot_{int(shot['shot']):02d}_{label.lower()}.png"
            compose_shot_plate(path, label=label, width=1080, height=1920, seed=2016 + int(shot["shot"]))
            card = out_dir / f"shot_{int(shot['shot']):02d}_card.json"
            card.write_text(
                json.dumps(
                    {
                        **shot,
                        "frame": str(path),
                        "visual_kind": "procedural_phone_cam",
                        "safe_area": {"top": 180, "bottom": 220, "left": 64, "right": 64},
                    },
                    indent=2,
                )
            )
            frames.append(
                {
                    "shot": shot["shot"],
                    "frame": str(path),
                    "card": str(card),
                    "visual_kind": "procedural_phone_cam",
                    **shot,
                }
            )

    if video:
        from first_reel.video import generate_live_video_clips

        clips = generate_live_video_clips(out_dir, stills=frames, prefer=prefer_video)
        by_shot = {int(c["shot"]): c for c in clips}
        merged: list[dict[str, Any]] = []
        for item in frames:
            shot_n = int(item["shot"])
            clip = by_shot.get(shot_n)
            if not clip:
                merged.append(item)
                continue
            merged.append({**item, **clip, "frame": item.get("frame") or clip.get("frame"), "clip": clip["clip"]})
        return merged
    return frames
