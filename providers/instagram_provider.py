from __future__ import annotations

from typing import Any

from providers.base_provider import Provider


class InstagramProvider(Provider):
    def health_check(self) -> bool:
        return True

    def publish(self, video_path: str, caption: str) -> dict[str, Any]:
        raise NotImplementedError


class StubInstagramProvider(InstagramProvider):
    def publish(self, video_path: str, caption: str) -> dict[str, Any]:
        self.last_call_cost = 0.0
        return {
            "platform_post_id": "stub_ig_reel_1",
            "status": "published",
            "note": "Stub publish — real IG requires a public video URL",
        }


class InstagramGraphProvider(InstagramProvider):
    def __init__(self, access_token: str, user_id: str, temp_hosting_base_url: str | None):
        self.access_token = access_token
        self.user_id = user_id
        self.temp_hosting_base_url = temp_hosting_base_url

    def health_check(self) -> bool:
        return bool(self.access_token and self.user_id and self.temp_hosting_base_url)

    def publish(self, video_path: str, caption: str) -> dict[str, Any]:
        raise NotImplementedError(
            "InstagramGraphProvider.publish is not wired yet. "
            "Requires temporary public hosting for the video URL."
        )
