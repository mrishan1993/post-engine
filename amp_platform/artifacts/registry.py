from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class ArtifactRecord:
    artifact_id: str
    type: str
    uri: str
    source_service: str
    version: str = "1"
    parent_ids: list[str] = field(default_factory=list)
    content_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ArtifactRegistry:
    """Phase-0 in-memory + path registry. Persist to DB/S3 index in a later PRP."""

    def __init__(self) -> None:
        self._items: dict[str, ArtifactRecord] = {}

    def register(
        self,
        *,
        type: str,
        uri: str,
        source_service: str,
        version: str = "1",
        parent_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        content_hash: str | None = None,
    ) -> ArtifactRecord:
        path = Path(uri)
        if content_hash is None and path.exists() and path.is_file():
            content_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:32]
        record = ArtifactRecord(
            artifact_id=str(uuid4()),
            type=type,
            uri=uri,
            source_service=source_service,
            version=version,
            parent_ids=parent_ids or [],
            content_hash=content_hash,
            metadata=metadata or {},
        )
        self._items[record.artifact_id] = record
        return record

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        return self._items.get(artifact_id)

    def lineage(self, artifact_id: str) -> list[ArtifactRecord]:
        """Walk parent_ids upward."""
        out: list[ArtifactRecord] = []
        seen: set[str] = set()
        stack = [artifact_id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            item = self._items.get(current)
            if not item:
                continue
            out.append(item)
            stack.extend(item.parent_ids)
        return out

    def all(self) -> list[ArtifactRecord]:
        return list(self._items.values())


_registry: ArtifactRegistry | None = None


def get_artifact_registry() -> ArtifactRegistry:
    global _registry
    if _registry is None:
        _registry = ArtifactRegistry()
    return _registry
