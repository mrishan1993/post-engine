from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class TransientMusicError(Exception):
    pass


class PermanentMusicError(Exception):
    pass


@dataclass
class MusicSubmitResult:
    provider_job_id: str
    estimated_cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MusicProviderStatus:
    status: str
    result_uri: str | None = None
    actual_cost: float | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MusicGenerationProvider(ABC):
    name: str

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def validate_request(self, request: dict[str, Any]) -> list[str]:
        ...

    @abstractmethod
    def submit(self, request: dict[str, Any], *, seed: int | None = None) -> MusicSubmitResult:
        ...

    @abstractmethod
    def get_status(self, provider_job_id: str) -> MusicProviderStatus:
        ...

    def cancel(self, provider_job_id: str) -> bool:
        return False

    def get_result(self, provider_job_id: str) -> MusicProviderStatus:
        return self.get_status(provider_job_id)

    @abstractmethod
    def estimate_cost(self, request: dict[str, Any]) -> float:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...
