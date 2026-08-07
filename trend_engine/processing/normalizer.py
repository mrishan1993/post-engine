from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import TrendSignal
from trend_engine.collectors.base import RawSignal


def persist_signals(session: Session, raw_signals: list[RawSignal]) -> list[TrendSignal]:
    """Write raw collector output into trend_signals."""
    rows: list[TrendSignal] = []
    for raw in raw_signals:
        row = TrendSignal(
            source=raw.source,
            external_id=raw.external_id,
            title_or_query=raw.title_or_query,
            raw_metrics=raw.raw_metrics,
            region=raw.region,
            category=raw.category,
            collected_at=raw.collected_at,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows
