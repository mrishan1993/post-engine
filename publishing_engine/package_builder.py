from __future__ import annotations

from pathlib import Path
from typing import Any

from publishing_engine.profiles import get_platform_profile
from publishing_engine.providers.stub import PublishBlockedError
from publishing_engine.schemas import PlatformPostPackage, PublishingPlanSpec


def resolve_media_uri(plan: PublishingPlanSpec, platform: str, session=None) -> dict[str, Any]:
    """Prefer platform derivative artifact, else master path. Never invent media."""
    target = next((p for p in plan.platforms if p.platform == platform), None)
    artifact_id = (target.artifact_id if target else None) or plan.media.master_artifact_id
    uri = plan.media.storage_uri
    cover = plan.media.cover_storage_uri
    meta: dict[str, Any] = {
        "duration_sec": plan.media.duration_sec,
        "width": plan.media.width,
        "height": plan.media.height,
        "mime_type": plan.media.mime_type,
        "artifact_id": artifact_id,
    }

    if session and artifact_id:
        from db.models import RenderedArtifact

        row = session.get(RenderedArtifact, artifact_id)
        if row:
            uri = row.storage_uri
            meta.update(
                {
                    "duration_sec": float(row.duration_sec or 0) or meta.get("duration_sec"),
                    "width": row.width or meta.get("width"),
                    "height": row.height or meta.get("height"),
                    "mime_type": row.mime_type or meta.get("mime_type"),
                }
            )
        if plan.media.cover_artifact_id:
            from db.models import ImageArtifact

            cover_row = session.get(ImageArtifact, plan.media.cover_artifact_id)
            if cover_row:
                cover = cover_row.storage_uri

    if not uri:
        raise PublishBlockedError("INVALID_MEDIA", "no media uri or artifact resolved")
    if not Path(uri).exists():
        raise PublishBlockedError("INVALID_MEDIA", f"file missing: {uri}")
    return {"media_uri": uri, "cover_uri": cover, **meta}


def build_platform_package(
    plan: PublishingPlanSpec,
    platform: str,
    account_id: str,
    *,
    session=None,
) -> PlatformPostPackage:
    target = next((p for p in plan.platforms if p.platform == platform), None)
    media = resolve_media_uri(plan, platform, session=session)

    title = (target.title if target and target.title else None) or plan.metadata.title
    caption = (target.caption if target and target.caption else None) or plan.metadata.body
    if target and target.hashtags is not None:
        if isinstance(target.hashtags, list):
            tags = list(target.hashtags)
        else:
            tags = target.hashtags.flattened()
    else:
        tags = plan.hashtags.flattened()

    # Normalize hashtags
    norm_tags = []
    for t in tags:
        t = t.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = f"#{t}"
        norm_tags.append(t)

    # Compile caption with hashtags if not already present
    body = caption or ""
    missing = [t for t in norm_tags if t.lower() not in body.lower()]
    if missing:
        body = (body.rstrip() + "\n\n" + " ".join(missing)).strip()

    profile = get_platform_profile(platform)
    return PlatformPostPackage(
        platform=platform,  # type: ignore[arg-type]
        account_id=account_id,
        media_uri=media["media_uri"],
        cover_uri=media.get("cover_uri"),
        title=title,
        caption=body,
        hashtags=norm_tags,
        mentions=list(plan.metadata.mentions or []),
        content_type=str(profile.get("content_type") or "reel"),
        duration_sec=media.get("duration_sec"),
        width=media.get("width"),
        height=media.get("height"),
        metadata={
            "profile_id": profile["id"],
            "artifact_id": media.get("artifact_id"),
            "character_slug": plan.character_slug,
        },
    )


def validate_media_against_profile(package: PlatformPostPackage) -> list[str]:
    profile = get_platform_profile(package.platform)
    issues: list[str] = []
    path = Path(package.media_uri)
    if not path.exists():
        issues.append("media file missing")
        return issues
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > float(profile.get("max_file_size_mb") or 500):
        issues.append("file exceeds platform max size")
    dur = package.duration_sec
    if dur is not None:
        if dur < float(profile.get("min_duration_sec") or 0):
            issues.append("duration below platform minimum")
        if dur > float(profile.get("max_duration_sec") or 9999):
            issues.append("duration exceeds platform maximum")
    for field in profile.get("required_metadata") or []:
        if field == "caption" and not (package.caption or "").strip():
            issues.append("caption required")
        if field == "title" and not (package.title or "").strip():
            issues.append("title required")
    return issues
