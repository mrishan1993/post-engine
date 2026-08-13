from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SocialPublishingProvider(ABC):
    """Platform-agnostic publishing adapter. Core engine never embeds API details."""

    platform: str

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    def validate_post(self, package: dict[str, Any]) -> list[str]:
        ...

    @abstractmethod
    def upload_media(
        self, package: dict[str, Any], *, idempotency_key: str
    ) -> dict[str, Any]:
        """Return {external_media_id, status}."""

    @abstractmethod
    def publish(
        self,
        package: dict[str, Any],
        *,
        external_media_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Return {external_post_id, url?, status, raw?}."""

    @abstractmethod
    def schedule(
        self,
        package: dict[str, Any],
        *,
        publish_at_iso: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_post(self, external_post_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def delete_post(self, external_post_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_post_url(self, external_post_id: str) -> str | None:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...

    def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        """Optional — return refreshed credential fields."""
        return credentials
