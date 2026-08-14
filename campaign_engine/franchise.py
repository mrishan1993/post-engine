from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from db.models import CampaignEpisode, ContentSeries, Franchise


def detect_franchise(
    session: Session,
    *,
    campaign_id: str,
    series: ContentSeries,
    episodes: list[CampaignEpisode],
    baseline_views: float = 500_000,
) -> Franchise | None:
    """Identify when repeated strong performance suggests a scalable series."""
    published = [e for e in episodes if e.performance]
    if len(published) < 3:
        return None
    lifts = []
    ids = []
    for e in published:
        views = float((e.performance or {}).get("views") or 0)
        if views <= 0:
            continue
        lifts.append(views / baseline_views)
        ids.append(e.id)
    if len(lifts) < 3:
        return None
    # Require 3 consecutive episodes above 1.8× baseline
    strong = [x for x in lifts if x >= 1.8]
    if len(strong) < 3:
        return None
    conf = min(0.95, 0.55 + 0.1 * len(strong) + 0.05 * (sum(lifts) / len(lifts)))
    row = Franchise(
        id=str(uuid4()),
        campaign_id=campaign_id,
        series_id=series.id,
        name=f"{series.name} Franchise",
        status="detected",
        confidence=round(conf, 3),
        performance_basis={
            "episode_count": len(published),
            "lifts": [round(x, 3) for x in lifts],
            "baseline_views": baseline_views,
            "note": "Association-based franchise signal; requires human approval in V1",
        },
        source_episode_ids=ids,
    )
    session.add(row)
    session.flush()
    get_bus().publish(
        EventType.FRANCHISE_DETECTED,
        {
            "franchise_id": row.id,
            "series_id": series.id,
            "campaign_id": campaign_id,
            "confidence": conf,
        },
        producer="campaign-engine",
    )
    return row
