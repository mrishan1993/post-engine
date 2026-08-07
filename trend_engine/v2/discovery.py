from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import RawContent, TrendSignal
from trend_engine.collectors.base import RawSignal


def ingest_raw_content(
    session: Session,
    signals: list[TrendSignal] | list[RawSignal],
) -> list[RawContent]:
    """Layer 1: land discovered items in raw_content (patterns come later)."""
    rows: list[RawContent] = []
    for sig in signals:
        if isinstance(sig, TrendSignal):
            metrics = sig.raw_metrics or {}
            row = RawContent(
                source=sig.source,
                external_id=sig.external_id,
                title=sig.title_or_query,
                description=None,
                creator_handle=metrics.get("channel_title"),
                url=_url_for(sig.source, sig.external_id),
                platform_metadata={
                    "region": sig.region,
                    "category": sig.category,
                    **metrics,
                },
                collected_at=sig.collected_at,
                trend_signal_id=sig.id,
            )
        else:
            metrics = sig.raw_metrics or {}
            row = RawContent(
                source=sig.source,
                external_id=sig.external_id,
                title=sig.title_or_query,
                creator_handle=metrics.get("channel_title"),
                url=_url_for(sig.source, sig.external_id),
                platform_metadata={"region": sig.region, "category": sig.category, **metrics},
                collected_at=sig.collected_at,
            )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _url_for(source: str, external_id: str | None) -> str | None:
    if not external_id:
        return None
    if source == "youtube":
        return f"https://www.youtube.com/watch?v={external_id}"
    return None
