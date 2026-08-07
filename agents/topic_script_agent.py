from __future__ import annotations

import time
from typing import Any

from agents.base import Agent, AgentResult
from config.schema import VerticalConfig
from providers.llm_provider import LLMProvider


class TopicScriptAgent(Agent):
    name = "topic_script_agent"

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def run(
        self,
        video_run_id: int,
        vertical_config: VerticalConfig,
        context: dict[str, Any],
        attempt_number: int = 1,
    ) -> AgentResult:
        start = time.time()
        cfg = vertical_config.script_agent
        prompt = self.llm.render_template(
            cfg.system_prompt_template,
            context={
                "tone": cfg.tone,
                "brief": context["brief_text"],
                "max_words": cfg.max_script_length_words,
            },
        )
        response = self.llm.generate(prompt, max_tokens=800)
        parsed = self.llm.parse_structured(
            response,
            schema={"title": str, "description": str, "tags": list, "script": str},
        )
        return AgentResult(
            success=True,
            output=parsed,
            cost_usd=self.llm.last_call_cost,
            duration_ms=int((time.time() - start) * 1000),
        )
