from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RawSignal:
    source: str
    external_id: str | None
    title_or_query: str
    raw_metrics: dict[str, Any] = field(default_factory=dict)
    region: str | None = None
    category: str | None = None
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Collector(ABC):
    name: str

    @abstractmethod
    def collect(self) -> list[RawSignal]:
        ...

    def health_check(self) -> bool:
        return True
