from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from amp_platform.artifacts.registry import get_artifact_registry
from amp_platform.events import EventType, get_bus
from assembly_engine.renderer import AssemblyRenderer
from assembly_engine.resolve import MissingAssetError, resolve_spec_assets
from assembly_engine.schemas import AssemblySpecification
from assembly_engine.state import transition_assembly, transition_render
from assembly_engine.timeline import build_timeline
from assembly_engine.validation import (
    collect_source_hashes,
    sha256_file,
    validate_assembly_spec,
    validate_rendered_output,
)
from db.models import Assembly, RenderJob, RenderedArtifact

MAX_ATTEMPTS = 2


class AssemblyRenderExecutor:
    def __init__(self, session: Session):
        self.session = session
        self.renderer = AssemblyRenderer()

    def process(self, render_id: str) -> RenderJob:
        job = self.session.get(RenderJob, render_id)
        if not job:
            raise ValueError(f"render job {render_id} not found")
        assembly = self.session.get(Assembly, job.assembly_id)
        if not assembly:
            raise ValueError("assembly not found")

        get_bus().publish(
            EventType.RENDER_STARTED,
            {"render_id": job.id, "assembly_id": assembly.id},
            producer="assembly-engine",
        )
        job.started_at = datetime.now(timezone.utc)
        job.attempt = int(job.attempt or 0) + 1
        self.session.flush()

        try:
            return self._execute(job, assembly)
        except Exception as exc:  # noqa: BLE001
            if job.attempt < MAX_ATTEMPTS and self._retryable(exc):
                job.status = transition_render(job.status if job.status != "failed" else "failed", "retry")
                job.error = {"message": str(exc), "retryable": True}
                job.status = transition_render("retry", "validating")
                self.session.flush()
                return self._execute(job, assembly)
            job.status = "failed"
            job.error = {"message": str(exc), "type": type(exc).__name__}
            job.completed_at = datetime.now(timezone.utc)
            # Keep a previously completed assembly completed if a later export fails
            if assembly.status != "completed":
                if assembly.status == "rendering":
                    assembly.status = transition_assembly("rendering", "failed")
                elif assembly.status in {"draft", "validated"}:
                    assembly.status = "failed"
            self.session.flush()
            get_bus().publish(
                EventType.RENDER_FAILED,
                {"render_id": job.id, "error": job.error},
                producer="assembly-engine",
            )
            return job

    def _execute(self, job: RenderJob, assembly: Assembly) -> RenderJob:
        t0 = time.time()
        job.status = transition_render(job.status, "validating")
        job.progress = 5
        self.session.flush()

        spec = AssemblySpecification.model_validate(assembly.specification)
        issues = validate_assembly_spec(spec)
        if issues:
            raise ValueError("invalid assembly: " + "; ".join(issues))

        job.status = transition_render(job.status, "resolving_assets")
        job.progress = 15
        self.session.flush()

        missing = resolve_spec_assets(self.session, spec)
        if missing:
            raise MissingAssetError(missing)
        # Persist resolved URIs so re-renders are deterministic
        assembly.specification = spec.model_dump()
        self.session.flush()

        job.status = transition_render(job.status, "building_timeline")
        job.progress = 35
        self.session.flush()

        timeline = build_timeline(spec)
        source_hashes = collect_source_hashes(timeline)
        timeline.source_hashes = source_hashes
        assembly.timeline = timeline.model_dump()
        assembly.duration_sec = timeline.duration_sec
        if assembly.status in {"draft", "failed"}:
            assembly.status = transition_assembly(assembly.status, "validated")
        assembly.status = transition_assembly(assembly.status, "rendering")
        self.session.flush()

        get_bus().publish(
            EventType.RENDER_PROGRESS,
            {"render_id": job.id, "progress": 40},
            producer="assembly-engine",
        )

        job.status = transition_render(job.status, "rendering")
        job.progress = 45
        self.session.flush()

        def _progress(p: float) -> None:
            job.progress = min(90, 45 + p * 0.45)
            get_bus().publish(
                EventType.RENDER_PROGRESS,
                {"render_id": job.id, "progress": float(job.progress)},
                producer="assembly-engine",
            )
            self.session.flush()

        result = self.renderer.render(
            assembly_id=assembly.id,
            render_id=job.id,
            spec=spec,
            timeline=timeline,
            quality=job.quality,
            progress_cb=_progress,
        )
        job.ffmpeg_used = bool(result.get("ffmpeg_used"))
        job.ffmpeg_version = result.get("ffmpeg_version")
        job.parameters = {
            **(job.parameters or {}),
            "source_hashes": source_hashes,
            "platform_profile": result.get("platform_profile"),
            "latency_ms": int((time.time() - t0) * 1000),
        }

        job.status = transition_render(job.status, "validating_output")
        job.progress = 92
        self.session.flush()

        qa = validate_rendered_output(
            result["storage_uri"],
            expected_duration=float(timeline.duration_sec),
            expected_width=int(result["width"]),
            expected_height=int(result["height"]),
            expected_fps=float(result["fps"]),
        )
        if not qa.ok:
            raise ValueError(f"output validation failed: {qa.notes}")

        digest, size = sha256_file(result["storage_uri"])
        artifact = RenderedArtifact(
            id=str(uuid4()),
            render_id=job.id,
            assembly_id=assembly.id,
            artifact_type="final_video" if job.quality == "final" else f"{job.quality}_video",
            storage_uri=result["storage_uri"],
            mime_type=result.get("mime_type") or "video/mp4",
            width=result.get("width"),
            height=result.get("height"),
            fps=result.get("fps"),
            duration_sec=result.get("duration_sec"),
            video_codec=result.get("video_codec"),
            audio_codec=result.get("audio_codec"),
            file_size_bytes=size,
            sha256=digest,
            technical_qa=qa.model_dump(),
            render_metadata={
                "assembly_version": assembly.version,
                "ffmpeg_version": job.ffmpeg_version,
                "ffmpeg_used": job.ffmpeg_used,
                "platform_profile": result.get("platform_profile"),
                "quality": job.quality,
                "source_hashes": source_hashes,
            },
            lineage={
                **(assembly.lineage or {}),
                "assembly_id": assembly.id,
                "render_id": job.id,
                "content_id": assembly.content_id,
            },
        )
        self.session.add(artifact)

        job.status = transition_render(job.status, "completed")
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        job.error = None
        assembly.status = "completed"
        assembly.updated_at = datetime.now(timezone.utc)
        self.session.flush()

        get_artifact_registry().register(
            type="final_video",
            uri=result["storage_uri"],
            source_service="assembly-engine",
            metadata={"artifact_id": artifact.id, "render_id": job.id, "sha256": digest},
        )
        get_bus().publish(
            EventType.RENDER_COMPLETED,
            {
                "render_id": job.id,
                "assembly_id": assembly.id,
                "artifact_id": artifact.id,
                "duration_sec": float(artifact.duration_sec or 0),
            },
            producer="assembly-engine",
        )
        get_bus().publish(
            EventType.RENDER_ARTIFACT_CREATED,
            {
                "render_id": job.id,
                "assembly_id": assembly.id,
                "artifact_id": artifact.id,
                "storage_uri": artifact.storage_uri,
                "width": artifact.width,
                "height": artifact.height,
            },
            producer="assembly-engine",
        )
        get_bus().publish(
            EventType.RENDER_TECHNICAL_QA_COMPLETED,
            {
                "render_id": job.id,
                "artifact_id": artifact.id,
                "ok": True,
                "technical_score": qa.technical_score,
            },
            producer="assembly-engine",
        )
        self.session.flush()
        return job

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        msg = str(exc).lower()
        if isinstance(exc, MissingAssetError):
            return False
        if "invalid assembly" in msg or "validation failed" in msg:
            return False
        return any(k in msg for k in ("timeout", "ffmpeg", "network", "temporary"))
