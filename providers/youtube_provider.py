from __future__ import annotations

from typing import Any

from providers.base_provider import Provider


class YouTubeProvider(Provider):
    def health_check(self) -> bool:
        return True

    def publish(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        made_for_kids: bool,
        category: str,
    ) -> dict[str, Any]:
        raise NotImplementedError


class StubYouTubeProvider(YouTubeProvider):
    def publish(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        made_for_kids: bool,
        category: str,
    ) -> dict[str, Any]:
        self.last_call_cost = 0.0
        return {
            "platform_post_id": "stub_yt_video_1",
            "made_for_kids": made_for_kids,
            "category": category,
            "status": "published",
        }


class YouTubeDataAPIProvider(YouTubeProvider):
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    def health_check(self) -> bool:
        return all([self.client_id, self.client_secret, self.refresh_token])

    def publish(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        made_for_kids: bool,
        category: str,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "YouTubeDataAPIProvider.publish is not wired yet. "
            "Use PIPELINE_STUB_PROVIDERS=true for local runs."
        )
