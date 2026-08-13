from __future__ import annotations

from hashlib import sha256
from typing import Any
from uuid import uuid4

from publishing_engine.providers.base import SocialPublishingProvider


class StubSocialProvider(SocialPublishingProvider):
    """Deterministic offline publisher for Instagram / YouTube / TikTok."""

    def __init__(
        self,
        platform: str,
        *,
        fail_upload: bool = False,
        fail_publish: bool = False,
        fail_permanent: bool = False,
        fail_transient: bool = False,
    ):
        self.platform = platform
        self.fail_upload = fail_upload
        self.fail_publish = fail_publish
        self.fail_permanent = fail_permanent
        self.fail_transient = fail_transient
        self._posts: dict[str, dict[str, Any]] = {}
        self._media: dict[str, dict[str, Any]] = {}

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "reels": self.platform == "instagram",
            "shorts": self.platform == "youtube",
            "tiktok": self.platform == "tiktok",
            "scheduling": True,
            "custom_thumbnail": self.platform != "tiktok",
            "analytics": True,
            "delete": True,
            "stub": True,
        }

    def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]:
        token = credentials.get("access_token") or ""
        if not token:
            raise ValueError("missing access_token")
        return {
            "status": "active",
            "external_account_id": credentials.get("external_account_id")
            or f"{self.platform}_acct",
            "scopes": credentials.get("scopes") or ["publishing", "analytics"],
        }

    def validate_post(self, package: dict[str, Any]) -> list[str]:
        issues = []
        if not package.get("media_uri"):
            issues.append("media_uri required")
        if self.platform == "youtube" and not (package.get("title") or "").strip():
            issues.append("title required for youtube")
        if self.platform in {"instagram", "tiktok"} and not (package.get("caption") or "").strip():
            issues.append("caption required")
        return issues

    def upload_media(
        self, package: dict[str, Any], *, idempotency_key: str
    ) -> dict[str, Any]:
        if self.fail_permanent:
            raise PermanentPublishError("invalid media rejected by platform")
        if self.fail_upload or self.fail_transient:
            raise TransientPublishError("upload timeout")
        digest = sha256(f"{self.platform}:{idempotency_key}:{package.get('media_uri')}".encode()).hexdigest()[:16]
        media_id = f"{self.platform}_media_{digest}"
        self._media[media_id] = {"package": package, "idempotency_key": idempotency_key}
        return {"external_media_id": media_id, "status": "uploaded"}

    def publish(
        self,
        package: dict[str, Any],
        *,
        external_media_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if self.fail_permanent:
            raise PermanentPublishError("policy rejection")
        if self.fail_publish or self.fail_transient:
            raise TransientPublishError("429 rate limited")
        digest = sha256(f"{self.platform}:post:{idempotency_key}".encode()).hexdigest()[:16]
        post_id = f"{self.platform}_post_{digest}"
        url = self._url_for(post_id)
        payload = {
            "external_post_id": post_id,
            "external_media_id": external_media_id,
            "url": url,
            "status": "published",
            "raw": {"stub": True, "platform": self.platform, "idempotency_key": idempotency_key},
        }
        self._posts[post_id] = payload
        return payload

    def schedule(
        self,
        package: dict[str, Any],
        *,
        publish_at_iso: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return {
            "status": "scheduled",
            "publish_at": publish_at_iso,
            "idempotency_key": idempotency_key,
            "external_schedule_id": f"sched_{uuid4().hex[:10]}",
        }

    def get_post(self, external_post_id: str) -> dict[str, Any]:
        post = self._posts.get(external_post_id)
        if not post:
            # Deterministic verify for previously unknown ids (simulates platform GET)
            return {
                "external_post_id": external_post_id,
                "status": "published",
                "url": self._url_for(external_post_id),
                "exists": True,
            }
        return {**post, "exists": True}

    def delete_post(self, external_post_id: str) -> dict[str, Any]:
        self._posts.pop(external_post_id, None)
        return {"status": "deleted", "external_post_id": external_post_id}

    def get_post_url(self, external_post_id: str) -> str | None:
        post = self._posts.get(external_post_id)
        if post:
            return post.get("url")
        return self._url_for(external_post_id)

    def health_check(self) -> bool:
        return not self.fail_permanent

    def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return {
            **credentials,
            "access_token": credentials.get("access_token") or "refreshed_stub_token",
            "refreshed": True,
        }

    def _url_for(self, post_id: str) -> str:
        if self.platform == "instagram":
            return f"https://www.instagram.com/reel/{post_id}/"
        if self.platform == "youtube":
            return f"https://www.youtube.com/shorts/{post_id}"
        if self.platform == "tiktok":
            return f"https://www.tiktok.com/@stub/video/{post_id}"
        return f"https://example.com/p/{post_id}"


class TransientPublishError(Exception):
    """Retryable platform/network error."""


class PermanentPublishError(Exception):
    """Do not auto-retry (auth, policy, invalid media)."""


class PublishBlockedError(Exception):
    def __init__(self, reason: str, details: str | None = None):
        self.reason = reason
        self.details = details
        super().__init__(f"PUBLISH_BLOCKED:{reason}:{details or ''}")


class InstagramAdapter(StubSocialProvider):
    def __init__(self, **kwargs):
        super().__init__("instagram", **kwargs)


class YouTubeAdapter(StubSocialProvider):
    def __init__(self, **kwargs):
        super().__init__("youtube", **kwargs)


class TikTokAdapter(StubSocialProvider):
    def __init__(self, **kwargs):
        super().__init__("tiktok", **kwargs)
