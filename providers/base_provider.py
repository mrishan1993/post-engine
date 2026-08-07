from __future__ import annotations

from abc import ABC, abstractmethod


class Provider(ABC):
    last_call_cost: float = 0.0

    @abstractmethod
    def health_check(self) -> bool:
        ...

    def estimate_cost(self, **kwargs) -> float:
        return 0.0
