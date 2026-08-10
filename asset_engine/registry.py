from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.artifacts.registry import get_artifact_registry
from amp_platform.events import EventType, get_bus
from db.models import Asset, AssetRelationship


PRODUCTION_STATUSES = {"approved", "active"}


class AssetRegistry:
    """Central provider-agnostic asset registry (AMP Asset Engine)."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        asset_type: str,
        name: str | None = None,
        storage_uri: str | None = None,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        provider: str | None = None,
        provider_asset_id: str | None = None,
        status: str = "draft",
        parent_asset_id: str | None = None,
        quality: dict[str, Any] | None = None,
        owner: str | None = None,
        embedding: list[float] | None = None,
    ) -> Asset:
        asset = Asset(
            id=str(uuid4()),
            asset_type=asset_type,
            name=name,
            storage_uri=storage_uri,
            mime_type=mime_type,
            metadata_json=metadata or {},
            tags=tags or [],
            provider=provider,
            provider_asset_id=provider_asset_id,
            status=status,
            version=1,
            parent_asset_id=parent_asset_id,
            quality=quality,
            owner=owner,
            embedding=embedding,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(asset)
        self.session.flush()

        # Mirror into platform artifact registry for lineage
        if storage_uri:
            get_artifact_registry().register(
                type=asset_type,
                uri=storage_uri,
                source_service="asset-engine",
                parent_ids=[parent_asset_id] if parent_asset_id else [],
                metadata={"asset_id": asset.id, "name": name, "provider": provider},
            )

        get_bus().publish(
            EventType.ASSET_CREATED,
            {
                "asset_id": asset.id,
                "asset_type": asset_type,
                "name": name,
                "status": status,
            },
            producer="asset-engine",
        )
        return asset

    def get(self, asset_id: str) -> Asset | None:
        return self.session.get(Asset, asset_id)

    def set_status(self, asset_id: str, status: str) -> Asset:
        asset = self.get(asset_id)
        if not asset:
            raise ValueError(f"asset {asset_id} not found")
        asset.status = status
        asset.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return asset

    def new_version(
        self,
        asset_id: str,
        *,
        storage_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        provider: str | None = None,
    ) -> Asset:
        parent = self.get(asset_id)
        if not parent:
            raise ValueError(f"asset {asset_id} not found")
        return self.create(
            asset_type=parent.asset_type,
            name=parent.name,
            storage_uri=storage_uri or parent.storage_uri,
            mime_type=parent.mime_type,
            metadata={**(parent.metadata_json or {}), **(metadata or {})},
            tags=list(parent.tags or []),
            provider=provider or parent.provider,
            status="draft",
            parent_asset_id=parent.id,
            quality=parent.quality,
            owner=parent.owner,
        )

    def link(
        self,
        *,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        relationship_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRelationship:
        rel = AssetRelationship(
            id=str(uuid4()),
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relationship_type=relationship_type,
            metadata_json=metadata or {},
        )
        self.session.add(rel)
        self.session.flush()
        return rel

    def relations(
        self,
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        relationship_type: str | None = None,
    ) -> list[AssetRelationship]:
        q = select(AssetRelationship)
        if source_type:
            q = q.where(AssetRelationship.source_type == source_type)
        if source_id:
            q = q.where(AssetRelationship.source_id == source_id)
        if relationship_type:
            q = q.where(AssetRelationship.relationship_type == relationship_type)
        return list(self.session.scalars(q).all())

    def search(
        self,
        *,
        query: str | None = None,
        asset_type: str | None = None,
        tags: list[str] | None = None,
        status_in: set[str] | None = None,
        limit: int = 50,
    ) -> list[Asset]:
        """Metadata search (Phase 3 adds embedding similarity)."""
        q = select(Asset)
        if asset_type:
            q = q.where(Asset.asset_type == asset_type)
        if status_in:
            q = q.where(Asset.status.in_(list(status_in)))
        rows = list(self.session.scalars(q.limit(limit * 3)).all())
        if query:
            ql = query.lower()
            rows = [
                a
                for a in rows
                if ql in (a.name or "").lower()
                or ql in " ".join(a.tags or []).lower()
                or ql in str(a.metadata_json or {}).lower()
            ]
        if tags:
            tagset = set(t.lower() for t in tags)
            rows = [a for a in rows if tagset & {t.lower() for t in (a.tags or [])}]
        return rows[:limit]

    def score_asset(self, asset: Asset, *, emotion: str | None = None, style: str | None = None) -> float:
        score = 50.0
        if asset.status in PRODUCTION_STATUSES:
            score += 20.0
        quality = asset.quality or {}
        score += 20.0 * float(quality.get("character_similarity") or quality.get("generation_quality") or 0.5)
        tags = {t.lower() for t in (asset.tags or [])}
        if emotion and emotion.lower() in tags:
            score += 10.0
        if style and style.lower().replace(" ", "_") in tags:
            score += 8.0
        # Prefer newer versions slightly
        score += min(asset.version, 5)
        return round(score, 2)

    def register_file(
        self,
        path: str | Path,
        *,
        asset_type: str,
        name: str | None = None,
        tags: list[str] | None = None,
        status: str = "approved",
        provider: str = "local",
    ) -> Asset:
        p = Path(path)
        return self.create(
            asset_type=asset_type,
            name=name or p.name,
            storage_uri=str(p),
            mime_type=_mime_for(p),
            tags=tags,
            status=status,
            provider=provider,
        )


def _mime_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".json": "application/json",
    }.get(ext, "application/octet-stream")
