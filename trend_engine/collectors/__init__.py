from trend_engine.collectors.base import Collector, RawSignal
from trend_engine.collectors.google_trends_collector import GoogleTrendsCollector
from trend_engine.collectors.youtube_collector import YouTubeCollector

__all__ = [
    "Collector",
    "RawSignal",
    "YouTubeCollector",
    "GoogleTrendsCollector",
]
