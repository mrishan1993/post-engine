from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from agents.base import Agent, AgentResult
from config.schema import VerticalConfig


class AssemblyAgent(Agent):
    name = "assembly_agent"

    def run(
        self,
        video_run_id: int,
        vertical_config: VerticalConfig,
        context: dict[str, Any],
        attempt_number: int = 1,
    ) -> AgentResult:
        start = time.time()
        cfg = vertical_config.assembly_agent
        output_path = Path(f"storage/rendered/{video_run_id}.mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        visual = Path(context["visual_asset_path"])
        audio = Path(context["audio_asset_path"])

        if not shutil.which("ffmpeg"):
            # Offline-friendly fallback: copy visual placeholder as "rendered" artifact
            shutil.copyfile(visual, output_path)
            return AgentResult(
                success=True,
                output={"rendered_video_path": str(output_path), "ffmpeg_used": False},
                cost_usd=0.0,
                duration_ms=int((time.time() - start) * 1000),
            )

        # Prefer muxing visual+audio when intro/outro templates are missing (Phase-1).
        intro = Path(cfg.intro_template)
        outro = Path(cfg.outro_template)
        if intro.exists() and outro.exists() and visual.suffix == ".mp4":
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(intro),
                "-i",
                str(visual),
                "-i",
                str(audio),
                "-i",
                str(outro),
                "-filter_complex",
                "[0:v][1:v][3:v]concat=n=3:v=1:a=0[v];[2:a]anull[a]",
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-s",
                cfg.target_resolution,
                str(output_path),
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(visual),
                "-i",
                str(audio),
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                "-s",
                cfg.target_resolution,
                str(output_path),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return AgentResult(
                success=False,
                error=result.stderr[-2000:] if result.stderr else "ffmpeg failed",
                duration_ms=int((time.time() - start) * 1000),
            )
        return AgentResult(
            success=True,
            output={"rendered_video_path": str(output_path), "ffmpeg_used": True},
            cost_usd=0.0,
            duration_ms=int((time.time() - start) * 1000),
        )
