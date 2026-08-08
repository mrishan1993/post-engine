from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from amp_platform.events.envelope import EventEnvelope
from amp_platform.events.types import EventType

logger = logging.getLogger(__name__)

Handler = Callable[[EventEnvelope], None]


class EventBus:
    """Phase-0 in-process bus. Same envelopes will publish to Redis Streams later."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._history: list[EventEnvelope] = []

    def subscribe(self, event_type: str | EventType, handler: Handler) -> None:
        self._handlers[str(event_type)].append(handler)

    def publish(
        self,
        event_type: str | EventType,
        payload: dict[str, Any] | Any,
        *,
        producer: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> EventEnvelope:
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        envelope = EventEnvelope(
            event_type=str(event_type),
            producer=producer,
            payload=dict(payload),
            correlation_id=correlation_id or str(uuid4()),
            causation_id=causation_id,
        )
        self._history.append(envelope)
        for handler in list(self._handlers.get(envelope.event_type, [])):
            try:
                handler(envelope)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Event handler failed type=%s producer=%s",
                    envelope.event_type,
                    producer,
                )
        for handler in list(self._handlers.get("*", [])):
            try:
                handler(envelope)
            except Exception:  # noqa: BLE001
                logger.exception("Wildcard handler failed type=%s", envelope.event_type)
        return envelope

    @property
    def history(self) -> list[EventEnvelope]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_bus() -> None:
    global _bus
    _bus = EventBus()
