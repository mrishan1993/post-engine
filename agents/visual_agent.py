from __future__ import annotations

import importlib
import time
from typing import Any

from agents.base import Agent, AgentResult
from config.schema import VerticalConfig


class VisualAgent(Agent):
    name = "visual_agent"

    def run(
        self,
        video_run_id: int,
        vertical_config: VerticalConfig,
        context: dict[str, Any],
        attempt_number: int = 1,
    ) -> AgentResult:
        start = time.time()
        compositor_module = importlib.import_module(f"rigs.{vertical_config.slug}.compositor")
        visual_path = compositor_module.render(
            audio_path=context["audio_asset_path"],
            audio_duration_sec=context["audio_duration_sec"],
            output_dir=f"storage/raw/{video_run_id}/",
        )
        return AgentResult(
            success=True,
            output={"visual_asset_path": visual_path},
            cost_usd=0.0,
            duration_ms=int((time.time() - start) * 1000),
        )
