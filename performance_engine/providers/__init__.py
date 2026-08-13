from __future__ import annotations

from performance_engine.providers.base import (
    AnalyticsProvider,
    InstagramAnalyticsAdapter,
    TikTokAnalyticsAdapter,
    YouTubeAnalyticsAdapter,
)

_PROVIDERS: dict[str, AnalyticsProvider] | None = None


def _defaults() -> dict[str, AnalyticsProvider]:
    return {
        "instagram": InstagramAnalyticsAdapter(),
        "youtube": YouTubeAnalyticsAdapter(),
        "tiktok": TikTokAnalyticsAdapter(),
    }


def get_analytics_provider(platform: str) -> AnalyticsProvider:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _defaults()
    if platform not in _PROVIDERS:
        raise ValueError(f"unsupported analytics platform: {platform}")
    return _PROVIDERS[platform]


def inject_analytics_provider(platform: str, provider: AnalyticsProvider) -> None:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _defaults()
    _PROVIDERS[platform] = provider


def reset_analytics_providers() -> None:
    global _PROVIDERS
    _PROVIDERS = None
