from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from first_reel.plates import write_shot_frames
from first_reel.spec import reel_spec


def write_reel_package(out_dir: Path, *, lineage: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Write the first-reel deliverable package (spec + phone-cam plates + lineage)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = reel_spec()
    frames = write_shot_frames(out_dir / "frames")
    package = {
        "reel": "first_reel_2016_phone",
        "spec": spec,
        "frames": frames,
        "lineage": lineage,
        "job": job,
        "audio_strategy": {
            "mode": "platform_native",
            "trend_audio": True,
            "status": "deferred_to_operator_at_publish",
            "instruction": (
                "At Instagram publish time, select the currently trending native audio "
                "associated with the 2016 nostalgia wave. Do not bake a downloaded "
                "copyrighted track into the master."
            ),
        },
        "qa_checklist": {
            "hook_without_audio": True,
            "first_frame_understandable": True,
            "punchline_lands": True,
            "loop_works": True,
            "aspect": "1080x1920",
            "duration_sec": 13,
            "trend_still_active_at_publish": True,
        },
        "note": (
            "Procedural phone-cam plates (unlock / selfie / status / montage) — "
            "silent master; native audio attaches at publish."
        ),
    }
    path = out_dir / "reel_package.json"
    path.write_text(json.dumps(package, indent=2, default=str))
    (out_dir / "caption.txt").write_text(spec["caption"] + "\n" + " ".join(spec["hashtags"]) + "\n")
    return {"package_path": str(path), "frames_dir": str(out_dir / "frames"), "package": package}
