from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from providers.base_provider import Provider

ROOT = Path(__file__).resolve().parent.parent


class LLMProvider(Provider):
    def health_check(self) -> bool:
        return True

    def render_template(self, template_path: str, context: dict[str, Any]) -> str:
        path = Path(template_path)
        if not path.is_absolute():
            path = ROOT / path
        text = path.read_text(encoding="utf-8")
        for key, value in context.items():
            text = text.replace("{{ " + key + " }}", str(value))
            text = text.replace("{{" + key + "}}", str(value))
        return text

    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        raise NotImplementedError

    def parse_structured(self, response: str, schema: dict[str, type]) -> dict[str, Any]:
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        data = json.loads(text)
        for key, expected in schema.items():
            if key not in data:
                raise ValueError(f"Missing key in LLM response: {key}")
            if expected is list and not isinstance(data[key], list):
                raise TypeError(f"Expected list for {key}")
            if expected is str and not isinstance(data[key], str):
                raise TypeError(f"Expected str for {key}")
        return data

    def classify_content(self, text: str, categories: list[str]) -> dict[str, float]:
        raise NotImplementedError


class StubLLMProvider(LLMProvider):
    """Deterministic offline LLM for local/CI runs."""

    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        self.last_call_cost = 0.02
        brief_match = re.search(r"Brief:\s*(.+)", prompt)
        brief = brief_match.group(1).strip() if brief_match else "a friendly rhyme"
        payload = {
            "title": f"Stub: {brief[:40]}",
            "description": f"An auto-generated stub video about {brief}.",
            "tags": ["kids", "rhyme", "stub"],
            "script": (
                f"Hello little friends! Today we learn about {brief}. "
                "Red and blue, me and you. Clap along and smile too!"
            ),
        }
        return json.dumps(payload)

    def classify_content(self, text: str, categories: list[str]) -> dict[str, float]:
        self.last_call_cost = 0.01
        scores = {cat: 0.0 for cat in categories}
        lowered = text.lower()
        if any(word in lowered for word in ("blood", "kill", "weapon")):
            if "violence" in scores:
                scores["violence"] = 0.4
        return scores


class AnthropicLLMProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def health_check(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        # Real Anthropic wiring lands when API keys are configured.
        # Keep stubbed body so Phase-1 skeleton stays runnable.
        raise NotImplementedError(
            "AnthropicLLMProvider.generate is not wired yet. "
            "Set PIPELINE_STUB_PROVIDERS=true or implement the Anthropic client call."
        )

    def classify_content(self, text: str, categories: list[str]) -> dict[str, float]:
        raise NotImplementedError(
            "AnthropicLLMProvider.classify_content is not wired yet."
        )
