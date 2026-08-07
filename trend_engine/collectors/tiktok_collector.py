from __future__ import annotations

from trend_engine.collectors.base import Collector, RawSignal


class TikTokCollector(Collector):
    """Placeholder — enable after Developer API access decision (PRP §11)."""

    name = "tiktok"

    def __init__(self, *, enabled: bool = False):
        self.enabled = enabled

    def collect(self) -> list[RawSignal]:
        if not self.enabled:
            return []
        raise NotImplementedError(
            "TikTok collector deferred. Prefer TikTok for Developers API path."
        )
