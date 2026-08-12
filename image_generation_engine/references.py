from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Asset, ProviderReference
from image_generation_engine.schemas import REF_ROLE_SCORES, ImagePromptPackage, ImageReference


def rank_and_trim_references(
    refs: list[ImageReference],
    *,
    max_references: int,
) -> list[ImageReference]:
    """Select highest-value refs when provider limits apply."""
    scored = []
    for r in refs:
        base = REF_ROLE_SCORES.get(r.role, 0.5)
        scored.append((max(base, float(r.score or 0)), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:max_references]]


def validate_and_prepare_references(
    session: Session,
    package: ImagePromptPackage,
    *,
    provider: str,
    max_references: int = 5,
    preserve_identity: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate refs; map/create provider reference IDs. Never invent asset IDs."""
    issues: list[str] = []
    refs = list(package.references)

    if preserve_identity and package.character_constraints.get("preserve_identity"):
        has_char = any(r.role in {"character", "face", "full_body"} for r in refs)
        if package.generation.mode in {"reference_to_image", "image_to_image"} and not has_char:
            # Soft warning — not always fatal for text_to_image
            if package.generation.mode == "reference_to_image":
                issues.append("character_reference_required but no character reference provided")

    refs = rank_and_trim_references(refs, max_references=max_references)
    prepared: list[dict[str, Any]] = []

    for ref in refs:
        uri = ref.uri
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
                "score": float(ref.score or REF_ROLE_SCORES.get(ref.role, 0.5)),
                "provider_asset_id": mapping.provider_asset_id,
                "status": mapping.status,
            }
        )

    # Edit source / mask
    edit = package.edit or {}
    for key, role in (("source_artifact_id", "source"), ("mask_asset_id", "mask")):
        aid = edit.get(key)
        if not aid:
            continue
        if len(prepared) >= max_references:
            break
        mapping = _get_or_create_mapping(session, str(aid), provider)
        prepared.append(
            {
                "asset_id": str(aid),
                "role": role,
                "uri": None,
                "score": REF_ROLE_SCORES.get(role, 0.5),
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


def infer_mode(package: ImagePromptPackage) -> str:
    if package.edit or package.purpose == "edit":
        return "image_editing"
    roles = {r.role for r in package.references}
    if "source" in roles or package.generation.mode == "image_to_image":
        return "image_to_image"
    if roles & {"character", "face", "full_body", "environment", "style"}:
        if len(package.references) >= 2 or "character" in roles:
            return "reference_to_image"
        return "image_to_image"
    return "text_to_image"
