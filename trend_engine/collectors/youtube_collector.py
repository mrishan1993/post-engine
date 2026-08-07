from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from trend_engine.collectors.base import Collector, RawSignal


class YouTubeCollector(Collector):
    """YouTube Data API v3 — videos.list(chart=mostPopular)."""

    name = "youtube"
    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self,
        api_key: str | None,
        *,
        regions: list[str] | None = None,
        category_ids: list[str] | None = None,
        max_results: int = 15,
        stub: bool = False,
    ):
        self.api_key = api_key
        self.regions = regions or ["US"]
        self.category_ids = category_ids or ["24"]
        self.max_results = max_results
        self.stub = stub

    def health_check(self) -> bool:
        return self.stub or bool(self.api_key)

    def collect(self) -> list[RawSignal]:
        if self.stub or not self.api_key:
            return self._stub_signals()
        signals: list[RawSignal] = []
        for region in self.regions:
            for category_id in self.category_ids:
                signals.extend(self._fetch_most_popular(region, category_id))
        return signals

    def _fetch_most_popular(self, region: str, category_id: str) -> list[RawSignal]:
        params = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "regionCode": region,
            "videoCategoryId": category_id,
            "maxResults": self.max_results,
            "key": self.api_key,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{self.BASE}/videos", params=params)
            resp.raise_for_status()
            data = resp.json()

        out: list[RawSignal] = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            published = snippet.get("publishedAt")
            age_hours = _age_hours(published)
            views = int(stats.get("viewCount") or 0)
            velocity = views / max(age_hours, 1.0)
            out.append(
                RawSignal(
                    source="youtube",
                    external_id=item.get("id"),
                    title_or_query=snippet.get("title") or "",
                    region=region,
                    category=snippet.get("categoryId") or category_id,
                    raw_metrics={
                        "views": views,
                        "likes": int(stats.get("likeCount") or 0),
                        "comments": int(stats.get("commentCount") or 0),
                        "published_at": published,
                        "age_hours": age_hours,
                        "velocity_views_per_hour": velocity,
                        "channel_title": snippet.get("channelTitle"),
                        "category_id": snippet.get("categoryId") or category_id,
                        "tags": snippet.get("tags") or [],
                    },
                )
            )
        return out

    def _stub_signals(self) -> list[RawSignal]:
        now = datetime.now(timezone.utc)
        stubs: list[dict[str, Any]] = [
            {
                "id": "stub_yt_kids_1",
                "title": "ABC Song for Toddlers — Learn Letters Fast",
                "category": "27",
                "region": "US",
                "views": 420_000,
                "age_hours": 8,
                "tags": ["kids", "abc", "nursery"],
            },
            {
                "id": "stub_yt_kids_2",
                "title": "Colors Rhyme Dance Party for Kids",
                "category": "10",
                "region": "US",
                "views": 180_000,
                "age_hours": 5,
                "tags": ["kids", "colors", "rhyme"],
            },
            {
                "id": "stub_yt_horror_1",
                "title": "The Whispering Well — Short Horror Story",
                "category": "24",
                "region": "US",
                "views": 310_000,
                "age_hours": 6,
                "tags": ["horror", "scary", "story"],
            },
            {
                "id": "stub_yt_horror_2",
                "title": "True Creepy Narration: Empty Elevator",
                "category": "24",
                "region": "GB",
                "views": 95_000,
                "age_hours": 4,
                "tags": ["creepy", "horror", "narration"],
            },
        ]
        signals: list[RawSignal] = []
        for s in stubs:
            age = float(s["age_hours"])
            views = int(s["views"])
            signals.append(
                RawSignal(
                    source="youtube",
                    external_id=s["id"],
                    title_or_query=s["title"],
                    region=s["region"],
                    category=s["category"],
                    collected_at=now,
                    raw_metrics={
                        "views": views,
                        "likes": int(views * 0.04),
                        "comments": int(views * 0.002),
                        "published_at": (now - timedelta(hours=age)).isoformat(),
                        "age_hours": age,
                        "velocity_views_per_hour": views / age,
                        "channel_title": "Stub Channel",
                        "category_id": s["category"],
                        "tags": s["tags"],
                    },
                )
            )
        return signals


def _age_hours(published_at: str | None) -> float:
    if not published_at:
        return 24.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        return max((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 0.5)
    except ValueError:
        return 24.0
