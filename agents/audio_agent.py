from __future__ import annotations

import time
from typing import Any

from agents.base import Agent, AgentResult
from config.schema import VerticalConfig
from providers.music_provider import MusicProvider
from providers.tts_provider import TTSProvider


class AudioAgent(Agent):
    name = "audio_agent"

    def __init__(self, tts: TTSProvider, music: MusicProvider):
        self.tts = tts
        self.music = music

    def run(
        self,
        video_run_id: int,
        vertical_config: VerticalConfig,
        context: dict[str, Any],
        attempt_number: int = 1,
    ) -> AgentResult:
        start = time.time()
        cfg = vertical_config.audio_agent
        provider = self.tts if cfg.type == "narration" else self.music
        audio_path, duration_sec = provider.generate(
            script=context["script"],
            style_prompt=cfg.style_prompt,
            voice_id=cfg.voice_id,
            output_dir=f"storage/raw/{video_run_id}/",
        )
        return AgentResult(
            success=True,
            output={"audio_asset_path": audio_path, "audio_duration_sec": duration_sec},
            cost_usd=provider.last_call_cost,
            duration_ms=int((time.time() - start) * 1000),
        )
