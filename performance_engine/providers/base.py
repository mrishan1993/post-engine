from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from hashlib import sha256
from math import exp
from typing import Any

from performance_engine.schemas import (
    AdapterFetchResult,
    AudienceData,
    CanonicalMetrics,
    RetentionPoint,
)


class AnalyticsProvider(ABC):
    platform: str

    @abstractmethod
    def get_post_metrics(
        self,
        external_post_id: str,
        *,
        age_since_publish_sec: int,
        growth_profile: str = "normal",
        seed: str | None = None,
    ) -> AdapterFetchResult:
        ...

    @abstractmethod
    def get_retention(
        self, external_post_id: str, *, duration_sec: float = 30.0
    ) -> list[RetentionPoint]:
        ...

    @abstractmethod
    def get_audience(self, external_post_id: str) -> AudienceData:
        ...

    @abstractmethod
    def get_comments(self, external_post_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_status(self, external_post_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...


def _growth_factor(age_sec: int, profile: str) -> float:
    """Monotonic growth curve 0→1 for stub metrics."""
    hours = max(age_sec, 0) / 3600.0
    if profile == "viral":
        # Fast takeoff
        return 1.0 - exp(-hours / 2.0)
    if profile == "slow":
        return 1.0 - exp(-hours / 48.0)
    return 1.0 - exp(-hours / 12.0)


def _seed_int(seed: str) -> int:
    return int(sha256(seed.encode()).hexdigest()[:8], 16)


class StubAnalyticsProvider(AnalyticsProvider):
    """Deterministic offline metrics with time-based growth."""

    def __init__(self, platform: str, *, peak_views: int | None = None):
        self.platform = platform
        self.peak_views = peak_views or (2_400_000 if platform == "instagram" else 1_800_000)

    def get_post_metrics(
        self,
        external_post_id: str,
        *,
        age_since_publish_sec: int,
        growth_profile: str = "normal",
        seed: str | None = None,
    ) -> AdapterFetchResult:
        s = _seed_int(seed or f"{self.platform}:{external_post_id}")
        g = _growth_factor(age_since_publish_sec, growth_profile)
        # Mild seed variation ±15%
        mult = 0.85 + (s % 30) / 100.0
        peak = int(self.peak_views * mult)
        views = max(0, int(peak * g))
        likes = int(views * (0.06 + (s % 20) / 1000))
        comments = int(views * 0.004)
        shares = int(views * (0.035 if growth_profile == "viral" else 0.018))
        saves = int(views * 0.015)
        reach = int(views * 0.78)
        nfr = int(reach * (0.72 if growth_profile == "viral" else 0.45))
        profile_visits = int(views * 0.02)
        followers = int(profile_visits * 0.11)
        completion = 0.62 + (0.18 if growth_profile == "viral" else 0.08) * min(1.0, g + 0.2)
        avg_watch = 18.0 + 8.0 * completion
        metrics = CanonicalMetrics(
            views=views,
            impressions=int(views * 1.15),
            reach=reach,
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
            average_watch_time_sec=round(avg_watch, 2),
            watch_time_sec=round(views * avg_watch, 2),
            completion_rate=round(min(0.95, completion), 4),
            profile_visits=profile_visits,
            followers_gained=followers,
            non_follower_reach=nfr,
            unique_viewers=int(views * 0.82) if views else 0,
            replays=max(0, views - int(views * 0.82)),
        )
        raw = {
            "platform": self.platform,
            "external_post_id": external_post_id,
            "stub": True,
            "growth_profile": growth_profile,
            "age_since_publish_sec": age_since_publish_sec,
            "metrics": metrics.model_dump(),
        }
        return AdapterFetchResult(
            raw_response=raw,
            endpoint=f"/{self.platform}/insights/{external_post_id}",
            http_status=200,
            metrics=metrics,
            retention=self.get_retention(external_post_id),
            audience=self.get_audience(external_post_id),
            platform_updated_at=datetime.now(timezone.utc),
        )

    def get_retention(
        self, external_post_id: str, *, duration_sec: float = 30.0
    ) -> list[RetentionPoint]:
        # Synthetic curve with a drop around 8–11s
        points = []
        for t in [0, 1, 2, 3, 5, 8, 11, 15, 20, 25, min(30, duration_sec)]:
            if t <= 3:
                pct = 100 - t * 2
            elif t <= 8:
                pct = 94 - (t - 3) * 1.5
            elif t <= 11:
                pct = 86.5 - (t - 8) * 8  # cliff
            else:
                pct = max(40.0, 62.5 - (t - 11) * 1.2)
            points.append(RetentionPoint(timestamp_sec=float(t), retention_percent=round(pct, 2)))
        return points

    def get_audience(self, external_post_id: str) -> AudienceData:
        return AudienceData(
            follower_count=125_000,
            non_follower_reach=None,  # filled from metrics when available
            demographics={"age_18_24": 0.42, "age_25_34": 0.31},
            geography={"IN": 0.55, "US": 0.18, "OTHER": 0.27},
        )

    def get_comments(self, external_post_id: str) -> dict[str, Any]:
        return {
            "count": 0,
            "items": [],
            "note": "comment intelligence deferred to separate engine",
        }

    def get_status(self, external_post_id: str) -> dict[str, Any]:
        return {"external_post_id": external_post_id, "status": "published", "exists": True}

    def health_check(self) -> bool:
        return True


class InstagramAnalyticsAdapter(StubAnalyticsProvider):
    def __init__(self, **kwargs):
        super().__init__("instagram", **kwargs)


class YouTubeAnalyticsAdapter(StubAnalyticsProvider):
    def __init__(self, **kwargs):
        super().__init__("youtube", peak_views=kwargs.pop("peak_views", 1_800_000), **kwargs)


class TikTokAnalyticsAdapter(StubAnalyticsProvider):
    def __init__(self, **kwargs):
        super().__init__("tiktok", peak_views=kwargs.pop("peak_views", 3_000_000), **kwargs)
