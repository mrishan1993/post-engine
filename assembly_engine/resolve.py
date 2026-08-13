from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from db.models import (
    AudioArtifact,
    AudioTimelineRow,
    ImageArtifact,
    VideoArtifact,
    VoiceArtifact,
    VoiceTimelineRow,
)


class MissingAssetError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"MISSING_ASSET: {', '.join(missing)}")


def resolve_storage_uri(session: Session, artifact_id: str) -> tuple[str, dict[str, Any]]:
    """Resolve artifact_id → (uri, metadata). Never invent paths."""
    for model, kind in (
        (VideoArtifact, "video"),
        (ImageArtifact, "image"),
        (VoiceArtifact, "voice"),
        (AudioArtifact, "audio"),
    ):
        row = session.get(model, artifact_id)
        if row:
            meta: dict[str, Any] = {
                "kind": kind,
                "artifact_id": row.id,
                "sha256": getattr(row, "sha256", None),
                "duration_sec": float(getattr(row, "duration_sec", None) or 0) or None,
            }
            if kind == "voice":
                meta["timestamps"] = row.timestamps
                meta["character_id"] = row.character_id
                meta["script_hash"] = row.script_hash
            if kind == "audio":
                meta["artifact_type"] = row.artifact_type
                meta["metadata"] = row.metadata_json
            return row.storage_uri, meta
        # prefix lookup
        from sqlalchemy import select

        rows = list(session.scalars(select(model).where(model.id.startswith(artifact_id))).all())
        if len(rows) == 1:
            return resolve_storage_uri(session, rows[0].id)

    raise MissingAssetError([artifact_id])


def verify_uris_exist(uris: list[str]) -> list[str]:
    missing = []
    for uri in uris:
        if not uri or not Path(uri).exists():
            missing.append(uri or "<empty>")
    return missing


def resolve_spec_assets(session: Session, spec: Any) -> list[str]:
    """Fill storage_uri on every clip. Returns list of missing artifact ids / uris.

    Never invents paths. Partial resolution is not enough — caller must abort render.
    """
    missing: list[str] = []
    clip_groups = (
        getattr(spec, "video_clips", None) or [],
        getattr(spec, "image_clips", None) or [],
        getattr(spec, "voice_clips", None) or [],
        getattr(spec, "music_clips", None) or [],
        getattr(spec, "sfx_clips", None) or [],
        getattr(spec, "ambience_clips", None) or [],
    )
    for clips in clip_groups:
        for clip in clips:
            uri = getattr(clip, "storage_uri", None)
            aid = getattr(clip, "artifact_id", None)
            if uri:
                if not Path(uri).exists():
                    missing.append(f"{aid or 'clip'}:{uri}")
                continue
            if not aid:
                missing.append("<clip without artifact_id or storage_uri>")
                continue
            try:
                resolved, meta = resolve_storage_uri(session, aid)
                clip.storage_uri = resolved
                clip.metadata = {**(getattr(clip, "metadata", None) or {}), **meta}
                if not Path(resolved).exists():
                    missing.append(f"{aid}:{resolved}")
            except MissingAssetError:
                missing.append(str(aid))
    return missing


def load_voice_timeline(session: Session, timeline_id: str) -> VoiceTimelineRow | None:
    row = session.get(VoiceTimelineRow, timeline_id)
    if row:
        return row
    from sqlalchemy import select

    rows = list(
        session.scalars(
            select(VoiceTimelineRow).where(VoiceTimelineRow.id.startswith(timeline_id))
        ).all()
    )
    return rows[0] if len(rows) == 1 else None


def load_audio_timeline(session: Session, timeline_id: str) -> AudioTimelineRow | None:
    row = session.get(AudioTimelineRow, timeline_id)
    if row:
        return row
    from sqlalchemy import select

    rows = list(
        session.scalars(
            select(AudioTimelineRow).where(AudioTimelineRow.id.startswith(timeline_id))
        ).all()
    )
    return rows[0] if len(rows) == 1 else None
