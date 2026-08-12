from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Asset, ProviderReference
from video_generation_engine.schemas import CharacterRefMode, VideoPromptPackage, VideoReference


def validate_and_prepare_references(
    session: Session,
    package: VideoPromptPackage,
    *,
    provider: str,
    character_mode: CharacterRefMode = "character_reference_optional",
    max_references: int = 4,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate refs; map/create provider reference IDs. Never invent asset IDs."""
    issues: list[str] = []
    refs = list(package.references)
    prepared: list[dict[str, Any]] = []

    if character_mode == "character_reference_required":
        has_char = any(r.role == "character" for r in refs)
        if not has_char:
            issues.append("character_reference_required but no character reference provided")

    if character_mode == "character_reference_disabled":
        refs = [r for r in refs if r.role != "character"]

    for ref in refs[:max_references]:
        uri = ref.uri
        asset = None
        # Only look up UUID-like asset ids
        if len(ref.asset_id) == 36 and ref.asset_id.count("-") == 4:
            asset = session.get(Asset, ref.asset_id)
            if asset:
                uri = uri or asset.storage_uri
            else:
                issues.append(f"asset not found: {ref.asset_id}")
                continue

        mapping = _get_or_create_mapping(session, ref.asset_id, provider)
        prepared.append(
            {
                "asset_id": ref.asset_id,
                "role": ref.role,
                "uri": uri,
                "provider_asset_id": mapping.provider_asset_id,
                "status": mapping.status,
            }
        )

    # Continuity / first-last frames from package
    frames = package.frames or {}
    for key in ("first_frame", "last_frame"):
        frame = frames.get(key)
        if isinstance(frame, dict) and frame.get("asset_id"):
            if len(prepared) >= max_references:
                break
            aid = str(frame["asset_id"])
            mapping = _get_or_create_mapping(session, aid, provider)
            prepared.append(
                {
                    "asset_id": aid,
                    "role": key,
                    "uri": frame.get("uri"),
                    "provider_asset_id": mapping.provider_asset_id,
                    "status": mapping.status,
                }
            )

    return prepared, issues


def _get_or_create_mapping(session: Session, asset_id: str, provider: str) -> ProviderReference:
    existing = session.scalar(
        select(ProviderReference).where(
            ProviderReference.internal_asset_id == asset_id,
            ProviderReference.provider == provider,
            ProviderReference.status == "active",
        )
    )
    if existing:
        return existing
    row = ProviderReference(
        id=str(uuid4()),
        internal_asset_id=asset_id,
        provider=provider,
        provider_asset_id=f"ref_{provider}_{asset_id[:8]}",
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


def infer_mode(package: VideoPromptPackage) -> str:
    roles = {r.role for r in package.references}
    if package.frames.get("first_frame") or "first_frame" in roles:
        return "image_to_video"
    if roles & {"character", "environment", "prop"} and len(package.references) >= 2:
        return "reference_to_video"
    if roles & {"character", "environment"}:
        return "image_to_video"
    return "text_to_video"
