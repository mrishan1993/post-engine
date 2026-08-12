from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class TransientGenerationError(Exception):
    """Retryable provider failure."""


class PermanentGenerationError(Exception):
    """Non-retryable provider failure."""


@dataclass
class SubmitResult:
    provider_job_id: str
    status: str = "submitted"
    estimated_cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderStatus:
    status: str  # submitted | processing | completed | failed
    progress: float = 0.0
    error: dict[str, Any] | None = None
    result_uri: str | None = None
    actual_cost: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class GenerationProvider(ABC):
    name: str
    modalities: list[str]

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...

    @abstractmethod
    def estimate_cost(self, prompt_package: dict[str, Any]) -> float:
        ...

    @abstractmethod
    def submit(
        self,
        prompt_package: dict[str, Any],
        *,
        seed: int | None = None,
        references: list[dict[str, Any]] | None = None,
    ) -> SubmitResult:
        ...

    @abstractmethod
    def get_status(self, provider_job_id: str) -> ProviderStatus:
        ...

    def cancel(self, provider_job_id: str) -> bool:
        return False

    def get_result(self, provider_job_id: str) -> ProviderStatus:
        return self.get_status(provider_job_id)
