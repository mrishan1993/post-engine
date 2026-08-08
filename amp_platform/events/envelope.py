from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Canonical AMP event envelope — all services must use this shape."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    producer: str
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    causation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_redis_fields(self) -> dict[str, str]:
        """Flatten for Redis Streams XADD (Phase-1 bus)."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "producer": self.producer,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id or "",
            "payload_json": self.model_dump_json(include={"payload"}),
        }
