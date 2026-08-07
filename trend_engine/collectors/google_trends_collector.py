from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from trend_engine.collectors.base import Collector, RawSignal


class GoogleTrendsCollector(Collector):
    """Google Trends interest via pytrends when available; stub otherwise."""

    name = "google_trends"

    def __init__(
        self,
        *,
        seed_queries: list[str] | None = None,
        geo: str = "",
        timeframe: str = "now 7-d",
        stub: bool = False,
    ):
        self.seed_queries = seed_queries or []
        self.geo = geo
        self.timeframe = timeframe
        self.stub = stub

    def health_check(self) -> bool:
        if self.stub:
            return True
        try:
            import pytrends  # noqa: F401
            return True
        except ImportError:
            return False

    def collect(self) -> list[RawSignal]:
        if self.stub:
            return self._stub_signals()
        try:
            return self._collect_pytrends()
        except Exception:
            # Fail soft — don't abort the whole daily run if Trends is flaky
            return self._stub_signals()

    def _collect_pytrends(self) -> list[RawSignal]:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=0)
        signals: list[RawSignal] = []
        # pytrends allows up to 5 keywords per build_payload
        for i in range(0, len(self.seed_queries), 5):
            batch = self.seed_queries[i : i + 5]
            pytrends.build_payload(batch, timeframe=self.timeframe, geo=self.geo)
            interest = pytrends.interest_over_time()
            if interest is None or interest.empty:
                continue
            for query in batch:
                if query not in interest.columns:
                    continue
                series = interest[query]
                latest = float(series.iloc[-1])
                mean = float(series.mean()) if len(series) else 0.0
                # Rising if latest > mean of window
                rising_ratio = (latest / mean) if mean > 0 else 0.0
                signals.append(
                    RawSignal(
                        source="google_trends",
                        external_id=query.lower().replace(" ", "_"),
                        title_or_query=query,
                        region=self.geo or "WW",
                        category="search_interest",
                        raw_metrics={
                            "interest_latest": latest,
                            "interest_mean": mean,
                            "rising_ratio": rising_ratio,
                            "timeframe": self.timeframe,
                        },
                    )
                )
        return signals

    def _stub_signals(self) -> list[RawSignal]:
        now = datetime.now(timezone.utc)
        stubs: list[dict[str, Any]] = [
            {"q": "kids nursery rhyme", "latest": 78.0, "mean": 55.0},
            {"q": "learning colors song", "latest": 72.0, "mean": 48.0},
            {"q": "scary story short", "latest": 81.0, "mean": 60.0},
            {"q": "horror narration", "latest": 68.0, "mean": 50.0},
            {"q": "bedtime story kids", "latest": 45.0, "mean": 52.0},
        ]
        return [
            RawSignal(
                source="google_trends",
                external_id=s["q"].lower().replace(" ", "_"),
                title_or_query=s["q"],
                region=self.geo or "WW",
                category="search_interest",
                collected_at=now,
                raw_metrics={
                    "interest_latest": s["latest"],
                    "interest_mean": s["mean"],
                    "rising_ratio": s["latest"] / s["mean"] if s["mean"] else 0.0,
                    "timeframe": self.timeframe,
                },
            )
            for s in stubs
        ]
