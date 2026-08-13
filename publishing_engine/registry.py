from __future__ import annotations

from publishing_engine.providers.base import SocialPublishingProvider
from publishing_engine.providers.stub import InstagramAdapter, TikTokAdapter, YouTubeAdapter

_PROVIDERS: dict[str, SocialPublishingProvider] | None = None


def _default_providers() -> dict[str, SocialPublishingProvider]:
    return {
        "instagram": InstagramAdapter(),
        "youtube": YouTubeAdapter(),
        "tiktok": TikTokAdapter(),
    }


def get_provider(platform: str) -> SocialPublishingProvider:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _default_providers()
    if platform not in _PROVIDERS:
        raise ValueError(f"unsupported platform: {platform}")
    return _PROVIDERS[platform]


def inject_provider(platform: str, provider: SocialPublishingProvider) -> None:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _default_providers()
    _PROVIDERS[platform] = provider


def reset_providers() -> None:
    global _PROVIDERS
    _PROVIDERS = None


def list_platforms() -> list[dict]:
    providers = _default_providers() if _PROVIDERS is None else _PROVIDERS
    return [
        {"platform": p, "capabilities": providers[p].get_capabilities(), "healthy": providers[p].health_check()}
        for p in providers
    ]
