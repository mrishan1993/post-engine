from __future__ import annotations

from trend_engine.collectors.base import Collector, RawSignal


class InstagramOwnCollector(Collector):
    """Owned-account Insights only via Graph API — not external discovery."""

    name = "instagram_own"

    def __init__(self, access_token: str | None = None, user_id: str | None = None):
        self.access_token = access_token
        self.user_id = user_id

    def health_check(self) -> bool:
        return bool(self.access_token and self.user_id)

    def collect(self) -> list[RawSignal]:
        if not self.health_check():
            return []
        raise NotImplementedError(
            "Instagram own-insights collector not wired yet. "
            "Requires Graph API media insights on owned content only."
        )
