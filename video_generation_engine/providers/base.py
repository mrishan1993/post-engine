from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class TransientVideoError(Exception):
    pass


class PermanentVideoError(Exception):
    pass


@dataclass
class VideoSubmitResult:
    provider_job_id: str
    estimated_cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoProviderStatus:
    status: str  # submitted | processing | completed | failed
    result_uri: str | None = None
    actual_cost: float | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VideoGenerationProvider(ABC):
    name: str

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def validate_request(self, request: dict[str, Any]) -> list[str]:
        ...

    @abstractmethod
    def prepare_references(self, references: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def submit(self, request: dict[str, Any], *, seed: int | None = None) -> VideoSubmitResult:
        ...

    @abstractmethod
    def get_status(self, provider_job_id: str) -> VideoProviderStatus:
        ...

    def cancel(self, provider_job_id: str) -> bool:
        return False

    def download_result(self, provider_job_id: str) -> VideoProviderStatus:
        return self.get_status(provider_job_id)

    @abstractmethod
    def estimate_cost(self, request: dict[str, Any]) -> float:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...
