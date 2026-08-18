from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from asset_engine.seed import seed_from_v2_config
from campaign_engine.schemas import CreateCampaignRequest
from campaign_engine.service import CampaignService
from config.settings import get_settings
from first_reel.gates import (
    check_audio_strategy,
    check_first_frame_hook,
    check_lineage,
    check_trend_freshness,
)
from first_reel.package import write_reel_package
from first_reel.spec import TREND_ID, creative_override, reel_spec
from orchestration_engine.schemas import CreateJobRequest, TrendOpportunityIn
from orchestration_engine.service import OrchestrationService
from strategy_engine.schemas import CreateStrategyRequest, IngestOpportunityRequest, StrategyProfile
from strategy_engine.service import StrategyService


def _write_first_learning(
    session: Session,
    *,
    lineage: dict[str, Any],
    job_status: str,
) -> dict[str, Any]:
    """AC12 — first learning written back (what we ask after Reel #1, not 'did it go viral?')."""
    from learning_engine.service import LearningService

    learning = {
        "reel": "first_reel_2016_phone",
        "question": "What did the system learn?",
        "hypotheses": [
            {
                "signal": "hook",
                "expectation": "strong",
                "note": "POV + year text readable without audio",
            },
            {
                "signal": "retention_after_5s",
                "expectation": "watch",
                "note": "If weak → increase cut frequency in montage",
            },
            {
                "signal": "shares_vs_follows",
                "expectation": "diagnose identity",
                "note": "High shares + low follows → strengthen recurring format/character",
            },
        ],
        "actions_for_reel_2": [
            "Measure 1s/3s retention and completion",
            "If middle sags: faster montage cuts",
            "If entertainment without follows: reinforce identity/franchise cue",
        ],
        "job_status": job_status,
        "lineage": {
            k: lineage.get(k)
            for k in (
                "content_id",
                "trend_id",
                "strategy_id",
                "campaign_id",
                "publication_id",
            )
        },
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    obs = LearningService(session).add_observation(
        {
            "feature_vector": {
                "source": "first_reel",
                "content_id": lineage.get("content_id"),
                "trend_id": lineage.get("trend_id"),
                "hook_type": "pov_nostalgia",
                "story_type": "phone_memory_reveal",
                "first_reel": True,
                "learning_brief": learning,
            },
            "outcome_vector": {
                "pending_performance": True,
                "publication_id": lineage.get("publication_id"),
            },
            "confidence": 0.55,
        }
    )
    get_bus().publish(
        EventType.ORCHESTRATION_LEARNING_HANDOFF,
        {"source": "first_reel", "observation": obs, "learning": learning},
        producer="first-reel",
    )
    return {"observation": obs, "learning": learning}


def run_first_reel(
    session: Session,
    *,
    character_slug: str = "ghost_kid",
    publish: bool = True,
    write_package: bool = True,
    live: bool = False,
) -> dict[str, Any]:
    """Vertical slice: Trend → Strategy → Campaign → Orchestrate → QA → Publish → Learn."""
    seed_from_v2_config(session)
    spec = reel_spec()
    trend = spec["trend"]

    fresh_ok, fresh_reason = check_trend_freshness(trend)
    if not fresh_ok:
        return {
            "ok": False,
            "failed_gate": "trend_freshness",
            "reason": fresh_reason,
            "acceptance": {},
        }

    strategy = StrategyService(session).create_strategy(
        CreateStrategyRequest(
            name="first_reel_nostalgia",
            character_slug=character_slug,
            profile=StrategyProfile(
                capacity={"reels_per_week": 7, "reels_per_day": 2},
            ),
            autonomy="semi_autonomous",
        )
    )
    opp = StrategyService(session).ingest_opportunity(
        IngestOpportunityRequest(
            strategy_id=strategy.strategy_id,
            source="trend",
            title=trend["title"],
            pillar="trend",
            platform="instagram",
            trend_id=TREND_ID,
            expiration_hours=36,
            payload={
                "opportunity_score": trend["opportunity_score"],
                "velocity_score": trend["velocity_score"],
                "freshness_score": trend["freshness_score"],
                "saturation_score": trend["saturation_score"],
                "viral_mechanism": trend["viral_mechanism"],
                "trend_stage": "accelerating",
                "category": trend["category"],
                "first_reel": True,
                **spec["opportunity"],
            },
        )
    )

    campaign = CampaignService(session).create_campaign(
        CreateCampaignRequest(
            name="First Reel — 2016 Phone",
            campaign_type="growth",
            character_slug=character_slug,
            strategy_id=strategy.strategy_id,
            episode_count=3,
            series_name="Nostalgia POV",
            series_premise="Phone-memory nostalgia beats",
            hypothesis="Nostalgia POV + loop outperforms generic trend slideshows",
            auto_decompose=True,
        )
    )

    override = creative_override()
    hook_ok, hook_issues = check_first_frame_hook(override["creative"])
    if not hook_ok:
        return {
            "ok": False,
            "failed_gate": "first_frame_hook",
            "reason": hook_issues,
            "acceptance": {},
        }

    job = OrchestrationService(session).create_job(
        CreateJobRequest(
            opportunity=TrendOpportunityIn(
                trend_id=TREND_ID,
                platform="instagram",
                trend_stage="accelerating",
                velocity_score=float(trend["velocity_score"]),
                freshness_score=float(trend["freshness_score"]),
                saturation_score=float(trend["saturation_score"]),
                opportunity_score=float(trend["opportunity_score"]),
                viral_mechanism=trend["viral_mechanism"],
                format="short_form_video",
                title=trend["title"],
                audience=["gen_z", "millennials", "nostalgia"],
                audio={
                    "audio_strategy": "platform_native",
                    "trend_audio": True,
                    "type": "platform_native_trend",
                },
                raw={
                    "first_reel": True,
                    "strategy_id": strategy.strategy_id,
                    "campaign_id": campaign.campaign_id,
                    "strategy_opportunity_id": opp.opportunity_id,
                    "spec": spec,
                },
            ),
            character_slug=character_slug,
            mode="autonomous",
            process=True,
            run_pipeline=True,
            lineage_extras={
                "first_reel": True,
                "strategy_id": strategy.strategy_id,
                "campaign_id": campaign.campaign_id,
                "strategy_opportunity_id": opp.opportunity_id,
            },
            creative_override=override,
            skip_publish_if_stale=True,
            min_publish_freshness=0.45,
        )
    )

    lineage = dict(job.lineage or {})
    # Normalize aliases for AC observability
    lineage.setdefault("creative_id", lineage.get("concept_id") or job.selected_concept_id)
    lineage.setdefault("qa_run_id", lineage.get("qa_id"))
    lineage.setdefault("assembly_run_id", lineage.get("assembly_id"))
    lineage["strategy_id"] = strategy.strategy_id
    lineage["campaign_id"] = campaign.campaign_id
    lineage["content_id"] = job.content_id
    lineage["trend_id"] = lineage.get("trend_id") or TREND_ID

    lineage_ok, missing = check_lineage(lineage)
    brief_audio = (job.brief.audio if job.brief else None) or override.get("audio")
    audio_ok = check_audio_strategy(brief_audio, lineage)

    package_info = None
    if write_package:
        out = Path(get_settings().storage_root) / "first_reel" / f"{job.content_id}"
        package_info = write_reel_package(
            out,
            lineage=lineage,
            job={
                "job_id": job.job_id,
                "status": job.status,
                "stage": job.current_stage,
                "publication_id": lineage.get("publication_id"),
            },
            live=live,
        )
        if live:
            try:
                from first_reel.live import generate_voiceover

                vo = generate_voiceover(out)
                if vo and package_info.get("package") is not None:
                    package_info["package"]["voiceover"] = vo
                    pkg_path = Path(package_info["package_path"])
                    pkg_path.write_text(
                        json.dumps(package_info["package"], indent=2, default=str)
                    )
            except Exception as exc:  # noqa: BLE001
                package_info["voiceover_error"] = str(exc)

    learning = None
    if lineage.get("publication_id") or job.status in {"PUBLISHED", "MEASURING", "LEARNING"}:
        learning = _write_first_learning(session, lineage=lineage, job_status=job.status)

    acceptance = {
        "AC1_trend_detected": True,
        "AC2_opportunity": opp.status in {"accepted", "evaluating", "production"},
        "AC3_creative_brief": bool(job.production_brief_id),
        "AC4_storyboard": bool(lineage.get("storyboard_id")),
        "AC5_assets": bool(lineage.get("asset_ids") or lineage.get("generation_run_id")),
        "AC6_assembled": bool(lineage.get("render_uri") or lineage.get("assembly_run_id")),
        "AC7_qa": bool(lineage.get("qa_run_id") or lineage.get("qa_id")),
        "AC8_platform_native_audio": audio_ok,
        "AC9_published": bool(lineage.get("publication_id")) if publish else None,
        "AC10_publication_id": bool(lineage.get("publication_id")),
        "AC11_performance": bool(lineage.get("performance_started")),
        "AC12_learning": bool(learning),
        "lineage_complete": lineage_ok,
        "lineage_missing": missing,
        "first_frame_hook": hook_ok,
        "trend_fresh": fresh_ok,
    }

    ok = all(
        v is True
        for k, v in acceptance.items()
        if k.startswith("AC") and v is not None and k != "AC9_published"
    ) and (acceptance["AC9_published"] is True if publish else True)

    return {
        "ok": ok and job.failure_reason is None,
        "job_id": job.job_id,
        "content_id": job.content_id,
        "status": job.status,
        "stage": job.current_stage,
        "failure_reason": job.failure_reason,
        "strategy_id": strategy.strategy_id,
        "campaign_id": campaign.campaign_id,
        "opportunity_id": opp.opportunity_id,
        "lineage": lineage,
        "acceptance": acceptance,
        "package": package_info,
        "learning": learning,
        "spec_name": spec["name"],
        "run_id": str(uuid4()),
    }
