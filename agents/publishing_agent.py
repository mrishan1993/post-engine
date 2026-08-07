from __future__ import annotations

import time
from typing import Any

from agents.base import Agent, AgentResult
from config.schema import VerticalConfig
from providers.instagram_provider import InstagramProvider
from providers.youtube_provider import YouTubeProvider


class PublishingAgent(Agent):
    name = "publishing_agent"

    def __init__(self, youtube: YouTubeProvider, instagram: InstagramProvider):
        self.youtube = youtube
        self.instagram = instagram

    def run(
        self,
        video_run_id: int,
        vertical_config: VerticalConfig,
        context: dict[str, Any],
        attempt_number: int = 1,
    ) -> AgentResult:
        start = time.time()
        cfg = vertical_config.publishing_agent
        results: dict[str, Any] = {}
        if "youtube" in cfg.platforms:
            results["youtube"] = self.youtube.publish(
                video_path=context["rendered_video_path"],
                title=context["title"],
                description=context["description"],
                tags=context["tags"],
                made_for_kids=cfg.youtube_made_for_kids,
                category=cfg.youtube_category,
            )
        if "instagram" in cfg.platforms:
            results["instagram"] = self.instagram.publish(
                video_path=context["rendered_video_path"],
                caption=context["description"],
            )
        return AgentResult(
            success=True,
            output={"publications": results},
            cost_usd=0.0,
            duration_ms=int((time.time() - start) * 1000),
        )
