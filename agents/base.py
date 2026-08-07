from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config.schema import VerticalConfig


@dataclass
class AgentResult:
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    duration_ms: int = 0
    error: str | None = None


class Agent(ABC):
    name: str

    @abstractmethod
    def run(
        self,
        video_run_id: int,
        vertical_config: VerticalConfig,
        context: dict[str, Any],
        attempt_number: int = 1,
    ) -> AgentResult:
        ...
