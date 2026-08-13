from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qa_engine.schemas import QaIssueSpec, QaPackage
from db.models import Assembly, RenderedArtifact, Story, Storyboard


def resolve_qa_package(
    session: Session,
    *,
    content_id: str | None = None,
    assembly_id: str | None = None,
    artifact_id: str | None = None,
    storage_uri: str | None = None,
    character_slug: str | None = None,
    prediction: dict[str, Any] | None = None,
    target_platforms: list[str] | None = None,
    force_safety_risk: str | None = None,
    injected_issues: list[QaIssueSpec] | None = None,
    package: QaPackage | None = None,
) -> QaPackage:
    if package is not None:
        pkg = package.model_copy(deep=True)
    else:
        pkg = QaPackage(content_id=content_id or "unknown")

    assembly: Assembly | None = None
    if assembly_id:
        assembly = session.get(Assembly, assembly_id)
        if not assembly:
            rows = list(
                session.scalars(select(Assembly).where(Assembly.id.startswith(assembly_id))).all()
            )
            assembly = rows[0] if len(rows) == 1 else None
    elif content_id:
        rows = list(
            session.scalars(
                select(Assembly)
                .where(Assembly.content_id == content_id)
                .order_by(Assembly.version.desc())
            ).all()
        )
        assembly = rows[0] if rows else None

    if assembly:
        pkg.content_id = pkg.content_id if pkg.content_id != "unknown" else assembly.content_id
        pkg.assembly_id = assembly.id
        pkg.specification = assembly.specification or {}
        pkg.timeline = assembly.timeline or {}
        pkg.platform_profile = assembly.platform_profile or pkg.platform_profile
        pkg.duration_sec = float(assembly.duration_sec or pkg.duration_sec or 0) or pkg.duration_sec
        pkg.lineage = {**(assembly.lineage or {}), **(pkg.lineage or {})}
        spec = pkg.specification
        pkg.captions = list(spec.get("captions") or pkg.captions)
        pkg.overlays = list(spec.get("overlays") or pkg.overlays)
        pkg.voice_clips = list(spec.get("voice_clips") or pkg.voice_clips)
        pkg.music_clips = list(spec.get("music_clips") or pkg.music_clips)
        pkg.sfx_clips = list(spec.get("sfx_clips") or pkg.sfx_clips)

        arts = list(
            session.scalars(
                select(RenderedArtifact)
                .where(RenderedArtifact.assembly_id == assembly.id)
                .order_by(RenderedArtifact.created_at.desc())
            ).all()
        )
        art = None
        if artifact_id:
            art = session.get(RenderedArtifact, artifact_id)
        if not art and arts:
            # Prefer final quality
            art = next((a for a in arts if a.artifact_type == "final_video"), arts[0])
        if art:
            pkg.artifact_id = art.id
            pkg.storage_uri = art.storage_uri
            pkg.width = art.width
            pkg.height = art.height
            pkg.fps = float(art.fps) if art.fps is not None else pkg.fps
            pkg.duration_sec = float(art.duration_sec or pkg.duration_sec or 0) or pkg.duration_sec
            pkg.video_codec = art.video_codec
            pkg.audio_codec = art.audio_codec
            pkg.technical_qa = art.technical_qa or {}

        if assembly.storyboard_id:
            board = session.get(Storyboard, assembly.storyboard_id)
            if board:
                pkg.storyboard = {
                    "id": board.id,
                    "story_id": board.story_id,
                    "duration_sec": float(board.duration_sec or 0),
                    "scenes": (board.document or {}).get("scenes") or [],
                    "document": board.document or {},
                }
                if board.story_id:
                    story = session.get(Story, board.story_id)
                    if story:
                        doc = story.blueprint or {}
                        pkg.story = {
                            "id": story.id,
                            "title": story.title,
                            "synopsis": story.logline or doc.get("synopsis") or doc.get("logline"),
                            "emotion": (
                                doc.get("emotional_arc")
                                or doc.get("emotion")
                                or (doc.get("creative_direction") or {}).get("emotion")
                            ),
                            "document": doc,
                        }
                        dialogue = []
                        for beat in doc.get("beats") or doc.get("scenes") or []:
                            if isinstance(beat, dict) and beat.get("dialogue"):
                                dialogue.append(str(beat["dialogue"]))
                        if dialogue and not pkg.expected_script:
                            pkg.expected_script = " ".join(dialogue)

    if storage_uri:
        pkg.storage_uri = storage_uri
    if character_slug:
        pkg.character_slug = character_slug
    if prediction:
        pkg.prediction = prediction
    if target_platforms:
        pkg.target_platforms = target_platforms
    if force_safety_risk:
        pkg.force_safety_risk = force_safety_risk  # type: ignore[assignment]
    if injected_issues:
        pkg.injected_issues = list(injected_issues)
    if not pkg.content_id or pkg.content_id == "unknown":
        pkg.content_id = content_id or pkg.assembly_id or "content_unknown"
    return pkg
