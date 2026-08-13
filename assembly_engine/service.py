from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from assembly_engine.builder import build_specification_from_assets
from assembly_engine.executor import AssemblyRenderExecutor
from assembly_engine.schemas import (
    AssemblySpecification,
    CreateAssemblyRequest,
    RenderRequestIn,
)
from assembly_engine.state import transition_assembly
from assembly_engine.timeline import build_timeline
from assembly_engine.validation import validate_assembly_spec
from db.models import Assembly, RenderJob, RenderedArtifact


class AssemblyService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, request: CreateAssemblyRequest | dict[str, Any]) -> Assembly:
        req = (
            request
            if isinstance(request, CreateAssemblyRequest)
            else CreateAssemblyRequest.model_validate(request)
        )

        if req.specification:
            spec = (
                req.specification
                if isinstance(req.specification, AssemblySpecification)
                else AssemblySpecification.model_validate(req.specification)
            )
        else:
            content_id = req.content_id or req.storyboard_id or str(uuid4())
            if not (
                req.video_artifact_ids
                or req.image_artifact_ids
                or req.voice_timeline_id
                or req.music_artifact_id
                or req.audio_timeline_id
            ):
                raise ValueError(
                    "specification or artifact refs (video/image/voice/music) required"
                )
            spec = build_specification_from_assets(
                self.session,
                content_id=content_id,
                storyboard_id=req.storyboard_id,
                video_artifact_ids=req.video_artifact_ids,
                image_artifact_ids=req.image_artifact_ids,
                voice_timeline_id=req.voice_timeline_id,
                music_artifact_id=req.music_artifact_id,
                audio_timeline_id=req.audio_timeline_id,
                platform_profile=req.platform_profile,
                captions_enabled=req.captions_enabled,
            )

        content_id = req.content_id or spec.content_id
        version = self._next_version(content_id)
        timeline = build_timeline(spec)

        row = Assembly(
            id=str(uuid4()),
            content_id=content_id,
            storyboard_id=req.storyboard_id or spec.storyboard_id,
            version=version,
            specification=spec.model_dump(),
            timeline=timeline.model_dump(),
            duration_sec=timeline.duration_sec,
            status="draft",
            platform_profile=spec.platform_profile,
            lineage=dict(spec.lineage or {}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()

        get_bus().publish(
            EventType.ASSEMBLY_CREATED,
            {
                "assembly_id": row.id,
                "content_id": content_id,
                "version": version,
                "duration_sec": float(row.duration_sec or 0),
            },
            producer="assembly-engine",
        )

        # Auto-validate
        self.validate(row.id)

        if req.process_render:
            self.render(
                RenderRequestIn(
                    assembly_id=row.id,
                    quality=req.render_quality,
                    process=True,
                )
            )
            self.session.refresh(row)
        return row

    def validate(self, assembly_id: str) -> Assembly:
        row = self._get_assembly(assembly_id)
        spec = AssemblySpecification.model_validate(row.specification)
        issues = validate_assembly_spec(spec)
        if issues:
            row.status = "failed"
            row.lineage = {**(row.lineage or {}), "validation_errors": issues}
            self.session.flush()
            raise ValueError("assembly validation failed: " + "; ".join(issues))
        row.status = transition_assembly(row.status, "validated")
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        get_bus().publish(
            EventType.ASSEMBLY_VALIDATED,
            {"assembly_id": row.id, "ok": True},
            producer="assembly-engine",
        )
        return row

    def update_specification(
        self, assembly_id: str, specification: AssemblySpecification | dict[str, Any]
    ) -> Assembly:
        old = self._get_assembly(assembly_id)
        spec = (
            specification
            if isinstance(specification, AssemblySpecification)
            else AssemblySpecification.model_validate(specification)
        )
        # Version up — never overwrite completed silently as same version for finals
        content_id = old.content_id
        version = self._next_version(content_id)
        timeline = build_timeline(spec)
        row = Assembly(
            id=str(uuid4()),
            content_id=content_id,
            storyboard_id=old.storyboard_id,
            version=version,
            specification=spec.model_dump(),
            timeline=timeline.model_dump(),
            duration_sec=timeline.duration_sec,
            status="draft",
            platform_profile=spec.platform_profile,
            lineage={**(old.lineage or {}), "previous_assembly_id": old.id},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.ASSEMBLY_UPDATED,
            {"assembly_id": row.id, "previous_assembly_id": old.id, "version": version},
            producer="assembly-engine",
        )
        return self.validate(row.id)

    def render(self, request: RenderRequestIn | dict[str, Any]) -> RenderJob:
        req = (
            request
            if isinstance(request, RenderRequestIn)
            else RenderRequestIn.model_validate(request)
        )
        assembly = self._get_assembly(req.assembly_id)
        if assembly.status == "draft":
            self.validate(assembly.id)
            self.session.refresh(assembly)

        profile = req.render_profile or assembly.platform_profile or "instagram_reels_v1"
        job = RenderJob(
            id=str(uuid4()),
            assembly_id=assembly.id,
            render_profile=profile,
            quality=req.quality,
            status="queued",
            progress=0,
            parameters={"priority": req.priority},
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(job)
        self.session.flush()

        get_bus().publish(
            EventType.RENDER_REQUESTED,
            {
                "render_id": job.id,
                "assembly_id": assembly.id,
                "quality": job.quality,
                "render_profile": job.render_profile,
            },
            producer="assembly-engine",
        )
        get_bus().publish(
            EventType.RENDER_QUEUED,
            {"render_id": job.id, "assembly_id": assembly.id},
            producer="assembly-engine",
        )

        if req.process:
            return AssemblyRenderExecutor(self.session).process(job.id)
        return job

    def get_assembly(self, assembly_id: str) -> Assembly | None:
        try:
            return self._get_assembly(assembly_id)
        except ValueError:
            return None

    def get_render(self, render_id: str) -> RenderJob | None:
        job = self.session.get(RenderJob, render_id)
        if job:
            return job
        rows = list(
            self.session.scalars(
                select(RenderJob).where(RenderJob.id.startswith(render_id))
            ).all()
        )
        return rows[0] if len(rows) == 1 else None

    def cancel_render(self, render_id: str) -> RenderJob:
        job = self.get_render(render_id)
        if not job:
            raise ValueError("render not found")
        if job.status in {"queued", "validating", "resolving_assets", "building_timeline"}:
            job.status = "cancelled"
            self.session.flush()
            get_bus().publish(
                EventType.RENDER_CANCELLED,
                {"render_id": job.id},
                producer="assembly-engine",
            )
        return job

    def list_artifacts(self, assembly_id: str) -> list[RenderedArtifact]:
        assembly = self._get_assembly(assembly_id)
        return list(
            self.session.scalars(
                select(RenderedArtifact)
                .where(RenderedArtifact.assembly_id == assembly.id)
                .order_by(RenderedArtifact.created_at.desc())
            ).all()
        )

    def _get_assembly(self, assembly_id: str) -> Assembly:
        row = self.session.get(Assembly, assembly_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(Assembly).where(Assembly.id.startswith(assembly_id))
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("assembly not found")
        return rows[0]

    def _next_version(self, content_id: str) -> int:
        rows = list(
            self.session.scalars(
                select(Assembly).where(Assembly.content_id == content_id)
            ).all()
        )
        if not rows:
            return 1
        return max(int(r.version) for r in rows) + 1


def create_assembly(
    session: Session, request: CreateAssemblyRequest | dict[str, Any]
) -> Assembly:
    return AssemblyService(session).create(request)
