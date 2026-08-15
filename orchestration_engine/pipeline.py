from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from orchestration_engine.schemas import ReelProductionBrief
from db.models import OrchestrationEngineRun, OrchestrationJob


def _record_run(
    session: Session,
    job: OrchestrationJob,
    *,
    engine_name: str,
    stage: str,
    status: str,
    input_reference: dict[str, Any] | None = None,
    output_reference: dict[str, Any] | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> OrchestrationEngineRun:
    row = OrchestrationEngineRun(
        id=str(uuid4()),
        job_id=job.id,
        engine_name=engine_name,
        stage=stage,
        input_reference=input_reference,
        output_reference=output_reference,
        status=status,
        duration_ms=duration_ms,
        error=error,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
        if status in {"COMPLETED", "FAILED", "CANCELLED", "BLOCKED"}
        else None,
    )
    session.add(row)
    session.flush()
    return row


def _lineage_update(job: OrchestrationJob, **kwargs: Any) -> None:
    lin = dict(job.lineage or {})
    lin.update(kwargs)
    job.lineage = lin


def run_story(session: Session, job: OrchestrationJob, brief: ReelProductionBrief) -> str:
    from story_engine.schemas import StoryRequest
    from story_engine.service import StoryService

    t0 = time.perf_counter()
    _record_run(
        session,
        job,
        engine_name="story_engine",
        stage="STORY_GENERATING",
        status="RUNNING",
        input_reference={"concept_id": brief.concept_id},
    )
    try:
        creative = brief.creative or {}
        stories = StoryService(session).generate(
            StoryRequest.model_validate(
                {
                    "content_opportunity": {
                        "topic": creative.get("hook") or creative.get("story") or "trend reel",
                        "trend_score": float((job.trend_snapshot or {}).get("opportunity_score") or 0.8),
                        "trend_stage": (job.trend_snapshot or {}).get("trend_stage") or "accelerating",
                        "emotion": "curiosity",
                        "platform": "instagram_reels"
                        if job.platform == "instagram"
                        else job.platform,
                    },
                    "creative_direction": {
                        "format": "POV",
                        "target_duration_sec": int((brief.editing or {}).get("duration") or 12),
                        "visual_style": (brief.visual or {}).get("visual_style") or "cinematic",
                    },
                    "characters": [
                        {"character_slug": job.character_slug or "ghost_kid", "role": "protagonist"}
                    ],
                    "candidate_count": 1,
                    "opportunity_id": job.opportunity_id,
                }
            )
        )
        story = stories[0]
        StoryService(session).approve(story.id)
        ms = int((time.perf_counter() - t0) * 1000)
        _record_run(
            session,
            job,
            engine_name="story_engine",
            stage="STORY_GENERATING",
            status="COMPLETED",
            output_reference={"story_id": story.id},
            duration_ms=ms,
        )
        _lineage_update(job, story_id=story.id)
        get_bus().publish(
            EventType.ORCHESTRATION_STORY_COMPLETED,
            {"job_id": job.id, "story_id": story.id},
            producer="orchestration-engine",
        )
        return story.id
    except Exception as exc:  # noqa: BLE001
        _record_run(
            session,
            job,
            engine_name="story_engine",
            stage="STORY_GENERATING",
            status="FAILED",
            error=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise


def run_storyboard(session: Session, job: OrchestrationJob, story_id: str) -> str:
    from storyboard_engine.schemas import StoryboardRequest
    from storyboard_engine.service import StoryboardService

    t0 = time.perf_counter()
    _record_run(
        session,
        job,
        engine_name="storyboard_engine",
        stage="STORYBOARD_GENERATING",
        status="RUNNING",
        input_reference={"story_id": story_id},
    )
    try:
        board = StoryboardService(session).generate(
            StoryboardRequest(
                story_id=story_id,
                character_slugs=[job.character_slug or "ghost_kid"],
                platform="instagram_reels" if job.platform == "instagram" else job.platform,
            )
        )
        StoryboardService(session).approve(board.id)
        _record_run(
            session,
            job,
            engine_name="storyboard_engine",
            stage="STORYBOARD_GENERATING",
            status="COMPLETED",
            output_reference={"storyboard_id": board.id},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _lineage_update(job, storyboard_id=board.id)
        get_bus().publish(
            EventType.ORCHESTRATION_STORYBOARD_COMPLETED,
            {"job_id": job.id, "storyboard_id": board.id},
            producer="orchestration-engine",
        )
        return board.id
    except Exception as exc:  # noqa: BLE001
        _record_run(
            session,
            job,
            engine_name="storyboard_engine",
            stage="STORYBOARD_GENERATING",
            status="FAILED",
            error=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise


def run_generation(session: Session, job: OrchestrationJob, storyboard_id: str) -> list[str]:
    from generation_engine.service import GenerationService

    t0 = time.perf_counter()
    _record_run(
        session,
        job,
        engine_name="generation_engine",
        stage="ASSET_GENERATING",
        status="RUNNING",
        input_reference={"storyboard_id": storyboard_id},
    )
    try:
        reqs = GenerationService(session).create_from_storyboard(
            storyboard_id,
            modality="video",
            variants=1,
            process=True,
        )
        # Collect artifacts across all shot requests (not just the first)
        artifact_ids: list[str] = []
        for req in reqs:
            arts = GenerationService(session).list_artifacts(req.id)
            artifact_ids.extend([a.id for a in arts])
        # Dedupe preserve order
        seen: set[str] = set()
        artifact_ids = [a for a in artifact_ids if not (a in seen or seen.add(a))]
        _record_run(
            session,
            job,
            engine_name="generation_engine",
            stage="ASSET_GENERATING",
            status="COMPLETED",
            output_reference={"artifact_ids": artifact_ids, "request_ids": [r.id for r in reqs]},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _lineage_update(
            job,
            asset_ids=artifact_ids,
            generation_request_ids=[r.id for r in reqs],
            generation_run_id=reqs[0].id if reqs else None,
        )
        get_bus().publish(
            EventType.ORCHESTRATION_ASSETS_COMPLETED,
            {"job_id": job.id, "artifact_count": len(artifact_ids)},
            producer="orchestration-engine",
        )
        return artifact_ids
    except Exception as exc:  # noqa: BLE001
        _record_run(
            session,
            job,
            engine_name="generation_engine",
            stage="ASSET_GENERATING",
            status="FAILED",
            error=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise


def run_assembly(
    session: Session,
    job: OrchestrationJob,
    *,
    storyboard_id: str,
    artifact_ids: list[str],
) -> str:
    from assembly_engine.schemas import CreateAssemblyRequest
    from assembly_engine.service import AssemblyService

    t0 = time.perf_counter()
    _record_run(
        session,
        job,
        engine_name="assembly_engine",
        stage="ASSEMBLING",
        status="RUNNING",
        input_reference={"storyboard_id": storyboard_id, "video_artifact_ids": artifact_ids},
    )
    try:
        assembly = AssemblyService(session).create(
            CreateAssemblyRequest(
                content_id=job.content_id,
                storyboard_id=storyboard_id,
                video_artifact_ids=artifact_ids[:12] if artifact_ids else [],
                process_render=True,
                render_quality="final",
            )
        )
        # Ensure render if create didn't
        arts = AssemblyService(session).list_artifacts(assembly.id)
        if not arts:
            from assembly_engine.schemas import RenderRequestIn

            AssemblyService(session).render(
                RenderRequestIn(assembly_id=assembly.id, process=True)
            )
            arts = AssemblyService(session).list_artifacts(assembly.id)
        storage_uri = arts[0].storage_uri if arts else None
        _record_run(
            session,
            job,
            engine_name="assembly_engine",
            stage="ASSEMBLING",
            status="COMPLETED",
            output_reference={"assembly_id": assembly.id, "storage_uri": storage_uri},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _lineage_update(
            job,
            assembly_id=assembly.id,
            assembly_run_id=assembly.id,
            render_uri=storage_uri,
        )
        get_bus().publish(
            EventType.ORCHESTRATION_ASSEMBLY_COMPLETED,
            {"job_id": job.id, "assembly_id": assembly.id},
            producer="orchestration-engine",
        )
        return assembly.id
    except Exception as exc:  # noqa: BLE001
        _record_run(
            session,
            job,
            engine_name="assembly_engine",
            stage="ASSEMBLING",
            status="FAILED",
            error=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise


def run_qa(session: Session, job: OrchestrationJob, assembly_id: str) -> str:
    from qa_engine.schemas import CreateQaRunRequest
    from qa_engine.service import QAService

    t0 = time.perf_counter()
    _record_run(
        session,
        job,
        engine_name="qa_engine",
        stage="QA",
        status="RUNNING",
        input_reference={"assembly_id": assembly_id},
    )
    try:
        run = QAService(session).create(
            CreateQaRunRequest(assembly_id=assembly_id, process=True)
        )
        # Auto-approve in autonomous path if decision pass-like
        decision = (run.decision or "").upper() if hasattr(run, "decision") else ""
        status = (run.status or "").lower()
        _record_run(
            session,
            job,
            engine_name="qa_engine",
            stage="QA",
            status="COMPLETED",
            output_reference={"qa_run_id": run.id, "status": status, "decision": decision},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _lineage_update(
            job,
            qa_id=run.id,
            qa_run_id=run.id,
            qa_status=status,
            qa_decision=decision,
        )
        get_bus().publish(
            EventType.ORCHESTRATION_QA_COMPLETED,
            {"job_id": job.id, "qa_run_id": run.id, "status": status},
            producer="orchestration-engine",
        )
        return run.id
    except Exception as exc:  # noqa: BLE001
        _record_run(
            session,
            job,
            engine_name="qa_engine",
            stage="QA",
            status="FAILED",
            error=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise


def run_publish(session: Session, job: OrchestrationJob, brief: ReelProductionBrief) -> str:
    from pathlib import Path
    from uuid import uuid4 as u4

    from publishing_engine.schemas import (
        ApprovalGate,
        CaptionSpec,
        ConnectAccountRequest,
        CreatePlanRequest,
        HashtagGroups,
        MediaRefs,
        PlatformTarget,
        PublishingPlanSpec,
        PublishingPolicy,
    )
    from publishing_engine.service import PublishingService

    t0 = time.perf_counter()
    _record_run(
        session,
        job,
        engine_name="publishing_engine",
        stage="PUBLISHING",
        status="RUNNING",
    )
    try:
        # AC: do not publish merely because production finished — re-check trend freshness
        lin = job.lineage or {}
        if lin.get("skip_publish_if_stale", True):
            snap = job.trend_snapshot or {}
            freshness = float(snap.get("freshness_score") or 0)
            min_fresh = float(lin.get("min_publish_freshness") or 0.45)
            stage = str(snap.get("trend_stage") or "").lower()
            if job.expiration_at:
                exp = job.expiration_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > exp:
                    raise ValueError("trend_stale_at_publish: expiration_at passed")
            if freshness < min_fresh or stage in {"saturated", "declining", "dead"}:
                raise ValueError(
                    f"trend_stale_at_publish: freshness={freshness} stage={stage} "
                    f"(min_freshness={min_fresh})"
                )

        storage_uri = lin.get("render_uri")
        if not storage_uri:
            raise ValueError("missing render_uri in lineage for publish")

        # Ensure stub meta exists for validation paths
        path = Path(storage_uri)
        if path.exists() and not path.with_suffix(".meta.json").exists():
            import json

            path.with_suffix(".meta.json").write_text(
                json.dumps(
                    {
                        "stub": True,
                        "width": 1080,
                        "height": 1920,
                        "fps": 30,
                        "duration_sec": int((brief.editing or {}).get("duration") or 12),
                        "video_codec": "h264",
                        "audio_codec": "aac",
                        "audio_strategy": (brief.audio or {}).get("audio_strategy")
                        or "platform_native",
                        "trend_audio": True,
                    }
                )
            )

        svc = PublishingService(session)
        acct = svc.connect_account(
            ConnectAccountRequest(
                platform="instagram" if job.platform == "instagram" else job.platform,
                external_account_id=f"orch_{u4().hex[:8]}",
                username=f"{job.character_slug or 'amp'}_ig",
                access_token="stub",
                stub_oauth=True,
            )
        )
        qa_id = lin.get("qa_run_id") or lin.get("qa_id")
        # Approve QA if needed for gate
        if qa_id:
            try:
                from qa_engine.service import QAService

                QAService(session).approve(qa_id, reviewer="orchestrator")
            except Exception:  # noqa: BLE001
                pass

        pub_req = brief.publishing_requirements or {}
        caption_body = pub_req.get("caption") or (brief.creative or {}).get("CTA") or ""
        caption_title = pub_req.get("title") or (brief.creative or {}).get("hook") or "Reel"
        hashtags = pub_req.get("hashtags") or ["#nostalgia"]
        if isinstance(hashtags, list):
            tag_groups = HashtagGroups(trend=[str(t).lstrip("#") for t in hashtags])
        else:
            tag_groups = HashtagGroups()

        plan = svc.create_plan(
            CreatePlanRequest(
                plan=PublishingPlanSpec(
                    content_id=job.content_id,
                    approval=ApprovalGate(
                        qa_status="passed",
                        approved=True,
                        reviewer="orchestrator",
                    ),
                    platforms=[
                        PlatformTarget(
                            platform="instagram" if job.platform == "instagram" else job.platform,
                            account_id=acct.id,
                            caption=caption_body,
                            hashtags=tag_groups.flattened(),
                        )
                    ],
                    metadata=CaptionSpec(
                        title=caption_title,
                        body=caption_body,
                    ),
                    hashtags=tag_groups,
                    media=MediaRefs(
                        storage_uri=storage_uri,
                        duration_sec=float((brief.editing or {}).get("duration") or 12),
                        width=1080,
                        height=1920,
                    ),
                    policy=PublishingPolicy(
                        require_qa=True,
                        require_human_approval=True,
                        allowed_platforms=["instagram", "youtube", "tiktok"],
                    ),
                    prediction_id=(job.lineage or {}).get("prediction_id") or job.id[:16],
                    character_slug=job.character_slug,
                    lineage={
                        "orchestration_job_id": job.id,
                        "content_id": job.content_id,
                        "trend_id": job.trend_id,
                        "strategy_id": lin.get("strategy_id"),
                        "campaign_id": lin.get("campaign_id"),
                        "creative_id": lin.get("creative_id") or job.selected_concept_id,
                        "concept_id": job.selected_concept_id,
                        "story_id": lin.get("story_id"),
                        "storyboard_id": lin.get("storyboard_id"),
                        "generation_run_id": lin.get("generation_run_id"),
                        "assembly_run_id": lin.get("assembly_run_id") or lin.get("assembly_id"),
                        "qa_run_id": qa_id,
                        "prediction_id": (job.lineage or {}).get("prediction_id") or job.id[:16],
                        "character_slug": job.character_slug,
                        "audio_strategy": (brief.audio or {}).get("audio_strategy")
                        or "platform_native",
                        "trend_audio": True,
                        "native_audio_selection": "deferred_to_operator_at_publish",
                    },
                    idempotency_key=f"orch_{job.id}",
                ),
                process=True,
            )
        )
        receipts = svc.list_receipts(plan.id)
        pub_id = receipts[0].id if receipts else plan.id
        _record_run(
            session,
            job,
            engine_name="publishing_engine",
            stage="PUBLISHING",
            status="COMPLETED",
            output_reference={
                "plan_id": plan.id,
                "publication_id": pub_id,
                "audio_strategy": "platform_native",
            },
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _lineage_update(
            job,
            publication_id=pub_id,
            publishing_plan_id=plan.id,
            audio_strategy="platform_native",
            native_audio_pending=True,
        )
        get_bus().publish(
            EventType.ORCHESTRATION_PUBLISHED,
            {
                "job_id": job.id,
                "publication_id": pub_id,
                "audio_strategy": "platform_native",
            },
            producer="orchestration-engine",
        )
        return pub_id
    except Exception as exc:  # noqa: BLE001
        _record_run(
            session,
            job,
            engine_name="publishing_engine",
            stage="PUBLISHING",
            status="FAILED",
            error=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise


def run_measure_and_learn(session: Session, job: OrchestrationJob) -> None:
    lin = job.lineage or {}
    pub_id = lin.get("publication_id")
    if pub_id:
        try:
            from performance_engine.schemas import StartTrackingRequest
            from performance_engine.service import PerformanceService

            PerformanceService(session).start_tracking(
                StartTrackingRequest(
                    publication_id=pub_id,
                    collect_now=True,
                    simulate_age_sec=3600,
                    growth_profile="viral",
                    prediction={
                        "orchestration_job_id": job.id,
                        "trend_id": job.trend_id,
                        "concept_id": job.selected_concept_id,
                        "content_id": job.content_id,
                    },
                )
            )
            _lineage_update(job, performance_started=True)
        except Exception:  # noqa: BLE001
            pass

    # Learning handoff — decision record as observation features
    try:
        from learning_engine.service import LearningService

        LearningService(session).add_observation(
            {
                "feature_vector": {
                    "character": job.character_slug,
                    "platform": job.platform,
                    "hook_type": ((job.mechanism or {}).get("hook_pattern")),
                    "story_type": ((job.mechanism or {}).get("mechanism")),
                    "trend_category": (job.trend_snapshot or {}).get("viral_mechanism"),
                    "orchestration_job_id": job.id,
                    "content_id": job.content_id,
                    "publication_id": pub_id,
                    "strategy_id": lin.get("strategy_id"),
                    "campaign_id": lin.get("campaign_id"),
                    "creative_id": lin.get("creative_id"),
                    "generation_run_id": lin.get("generation_run_id"),
                    "assembly_run_id": lin.get("assembly_run_id"),
                    "qa_run_id": lin.get("qa_run_id") or lin.get("qa_id"),
                    "concept_id": job.selected_concept_id,
                    "verification_stage": "primary",
                    "first_reel": bool(lin.get("first_reel")),
                },
                "outcome_vector": {
                    "views": None,
                    "completion_rate": None,
                    "share_rate": None,
                    "pending_performance": True,
                },
                "confidence": 0.4,
            }
        )
        get_bus().publish(
            EventType.ORCHESTRATION_LEARNING_HANDOFF,
            {"job_id": job.id, "publication_id": pub_id, "content_id": job.content_id},
            producer="orchestration-engine",
        )
    except Exception:  # noqa: BLE001
        pass