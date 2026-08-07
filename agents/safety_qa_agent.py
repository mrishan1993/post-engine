from __future__ import annotations

import time
from typing import Any

from agents.base import Agent, AgentResult
from config.schema import VerticalConfig
from providers.llm_provider import LLMProvider


class SafetyQAAgent(Agent):
    name = "safety_qa_agent"

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
        cfg = vertical_config.safety_qa
        classification = self.llm.classify_content(
            text=context["script"],
            categories=list(cfg.classifier_thresholds.keys()),
        )
        flags = {
            cat: score
            for cat, score in classification.items()
            if score > cfg.classifier_thresholds.get(cat, 1.0)
        }
        # Always routes to human review regardless of flags — PRP §9.
        return AgentResult(
            success=True,
            output={"safety_check_result": {"scores": classification, "flags": flags}},
            cost_usd=self.llm.last_call_cost,
            duration_ms=int((time.time() - start) * 1000),
        )
