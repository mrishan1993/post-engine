"""Shot frame writer for First Reel — procedural or live API stills."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from amp_platform.procedural_media import compose_shot_plate
from first_reel.spec import SHOTS


def write_shot_frames(out_dir: Path, *, live: bool = False) -> list[dict[str, Any]]:
    """Write one PNG per shot. When live=True, use Replicate/FAL/OpenAI/Gemini chain."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if live:
        from first_reel.live import generate_live_frames

        try:
            frames = generate_live_frames(out_dir)
            if frames and len(frames) >= len(SHOTS):
                return frames
        except Exception:  # noqa: BLE001
            # Fall through to procedural so packaging never hard-fails
            pass

    frames: list[dict[str, Any]] = []
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
    return frames
