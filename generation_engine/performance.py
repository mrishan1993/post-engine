from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ProviderPerformance


def record_outcome(
    session: Session,
    *,
    provider: str,
    model: str | None,
    modality: str,
    success: bool,
    latency_ms: int | None,
    cost: float | None,
    used_fallback: bool = False,
    qa_score: float | None = None,
) -> ProviderPerformance:
    row = session.scalar(
        select(ProviderPerformance).where(
            ProviderPerformance.provider == provider,
            ProviderPerformance.modality == modality,
            ProviderPerformance.model == model,
        )
    )
    if not row:
        row = ProviderPerformance(
            id=str(uuid4()),
            provider=provider,
            model=model,
            modality=modality,
            success_rate=1.0 if success else 0.0,
            avg_latency_ms=latency_ms,
            avg_cost=cost,
            avg_qa_score=qa_score,
            fallback_rate=1.0 if used_fallback else 0.0,
            sample_count=1,
            updated_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.flush()
        return row

    n = int(row.sample_count or 0)
    new_n = n + 1

    def ema(old: float | None, new: float | None, default: float = 0.0) -> float:
        if new is None:
            return float(old if old is not None else default)
        if old is None:
            return float(new)
        return (old * n + new) / new_n

    row.success_rate = ema(float(row.success_rate) if row.success_rate is not None else None, 1.0 if success else 0.0)
    row.avg_latency_ms = int(
        ema(
            float(row.avg_latency_ms) if row.avg_latency_ms is not None else None,
            float(latency_ms) if latency_ms is not None else None,
        )
    )
    row.avg_cost = ema(
        float(row.avg_cost) if row.avg_cost is not None else None,
        cost,
    )
    if qa_score is not None:
        row.avg_qa_score = ema(
            float(row.avg_qa_score) if row.avg_qa_score is not None else None,
            qa_score,
        )
    row.fallback_rate = ema(
        float(row.fallback_rate) if row.fallback_rate is not None else None,
        1.0 if used_fallback else 0.0,
    )
    row.sample_count = new_n
    row.updated_at = datetime.now(timezone.utc)
    session.flush()
    return row
