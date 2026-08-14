from __future__ import annotations

from amp_platform.events import EventType, get_bus, reset_bus
from campaign_engine.continuity import init_continuity, validate_continuity
from campaign_engine.narrative import cross_platform_adaptations, decompose_episodes
from campaign_engine.schemas import (
    CreateCampaignRequest,
    ExecuteEpisodeRequest,
    InjectTrendRequest,
    OptimizeCampaignRequest,
    RecordPerformanceRequest,
)
from campaign_engine.service import CampaignService
from db.session import get_session
from strategy_engine.schemas import CreateStrategyRequest, StrategyProfile
from strategy_engine.service import StrategyService


def test_decompose_and_cross_platform() -> None:
    eps = decompose_episodes(
        count=5,
        character_slug="alex",
        series_name="Alex Tries",
        premise="human things",
        platforms=["instagram", "tiktok"],
    )
    assert len(eps) == 5
    assert eps[0]["narrative_role"] == "introduction"
    assert eps[-1]["narrative_role"] == "finale"
    adapts = cross_platform_adaptations({"title": "T", "hook": "H"}, ["instagram", "tiktok", "youtube"])
    assert len(adapts) == 3
    assert {a["platform"] for a in adapts} == {"instagram", "tiktok", "youtube"}


def test_continuity_phone_warning() -> None:
    cont = init_continuity(character_slug="alex", campaign_name="Meet Alex")
    cont["story_facts"] = ["Ep3: Character loses phone"]
    warns = validate_continuity(cont, proposed_premise="Character uses phone normally")
    assert warns


def test_campaign_end_to_end(db_url: str) -> None:
    reset_bus()
    bus = get_bus()
    with get_session(db_url) as session:
        strategy = StrategyService(session).create_strategy(
            CreateStrategyRequest(
                name="growth",
                character_slug="ghost_kid",
                profile=StrategyProfile(),
            )
        )
        svc = CampaignService(session)
        campaign = svc.create_campaign(
            CreateCampaignRequest(
                name="Meet Alex",
                campaign_type="character",
                character_slug="ghost_kid",
                strategy_id=strategy.strategy_id,
                episode_count=5,
                series_name="Alex Tries Human Things",
                series_premise="Alex navigates everyday situations",
                auto_decompose=True,
            )
        )
        assert campaign.status == "active"
        assert len(campaign.series) == 1
        series = campaign.series[0]
        assert len(series.episodes) == 5
        assert series.episodes[0].narrative_role == "introduction"
        assert series.episodes[-1].narrative_role == "finale"

        # Sequencing dependencies exist
        from sqlalchemy import select
        from db.models import CampaignDependency

        deps = list(
            session.scalars(
                select(CampaignDependency).where(
                    CampaignDependency.campaign_id == campaign.campaign_id
                )
            ).all()
        )
        assert len(deps) == 4  # 5 episodes → 4 sequence edges

        # AC5 — trend injection into mid episode
        mid = series.episodes[2]
        injected = svc.inject_trend(
            InjectTrendRequest(
                campaign_id=campaign.campaign_id,
                series_id=series.series_id,
                episode_id=mid.episode_id,
                trend_id="trend_unexpected_reveal",
                viral_mechanism="unexpected_reveal",
            )
        )
        assert injected.trend_id == "trend_unexpected_reveal"
        assert injected.continuity_requirements.get("preserve_series_identity") is True

        # AC6 — cross-platform content rows
        from db.models import CampaignContent

        contents = list(
            session.scalars(
                select(CampaignContent).where(CampaignContent.campaign_id == campaign.campaign_id)
            ).all()
        )
        platforms = {c.platform for c in contents}
        assert "instagram" in platforms
        assert "tiktok" in platforms or "youtube" in platforms

        # AC11 — execute → orchestrator (+ strategy ingest)
        exec_out = svc.execute_episode(
            ExecuteEpisodeRequest(
                episode_id=series.episodes[0].episode_id,
                run_pipeline=False,
                orchestration_mode="autonomous",
                push_to_strategy=True,
            )
        )
        assert exec_out["orchestration_job_id"]
        assert exec_out["lineage"]["campaign_id"] == campaign.campaign_id
        assert exec_out["lineage"]["episode_id"] == series.episodes[0].episode_id
        assert exec_out.get("strategy_opportunity_id")

        # AC9 — performance per episode
        views = [400_000, 700_000, 1_100_000, 3_400_000, 2_700_000]
        for ep, v in zip(series.episodes, views, strict=True):
            svc.record_performance(
                RecordPerformanceRequest(episode_id=ep.episode_id, views=float(v), followers_gained=v / 100)
            )

        # AC7 + AC8 — replan + franchise detection
        opt = svc.optimize(OptimizeCampaignRequest(campaign_id=campaign.campaign_id))
        assert opt["campaign_id"] == campaign.campaign_id
        assert any(a["action"] == "franchise_detected" for a in opt["actions"]) or opt["franchises"]
        assert any(a["action"] == "extend_series" for a in opt["actions"])

        if opt["franchises"]:
            approved = svc.approve_franchise(opt["franchises"][0]["franchise_id"])
            assert approved.status == "approved"

        # AC12 — lineage
        lineage = svc.lineage(campaign.campaign_id, episode_id=series.episodes[0].episode_id)
        assert lineage["strategy_id"] == strategy.strategy_id
        assert lineage["campaign_id"]
        assert lineage["series_id"]
        assert lineage["episode_id"]

        # Decision log
        decisions = svc.decisions(campaign.campaign_id)
        types = {d["decision_type"] for d in decisions}
        assert "campaign_created" in types
        assert "trend_injected" in types

        # Events fired
        seen = {e.event_type for e in bus.history}
        assert EventType.CAMPAIGN_CREATED in seen
        assert EventType.SERIES_CREATED in seen
        assert EventType.EPISODE_CREATED in seen
        assert EventType.EPISODE_EXECUTION_REQUESTED in seen
        assert EventType.CAMPAIGN_PERFORMANCE_UPDATED in seen


def test_weak_series_retire(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        svc = CampaignService(session)
        campaign = svc.create_campaign(
            CreateCampaignRequest(
                name="Weak Test",
                character_slug="ghost_kid",
                episode_count=3,
                auto_decompose=True,
            )
        )
        series = campaign.series[0]
        for ep, v in zip(series.episodes, [900_000, 420_000, 180_000], strict=True):
            svc.record_performance(
                RecordPerformanceRequest(episode_id=ep.episode_id, views=float(v))
            )
        # Add a draft future episode then optimize retire
        from campaign_engine.schemas import CreateEpisodeRequest

        draft = svc.create_episode(
            CreateEpisodeRequest(
                series_id=series.series_id,
                premise="Another beat",
                narrative_role="escalation",
                audience_role="relationship",
            )
        )
        opt = svc.optimize(OptimizeCampaignRequest(campaign_id=campaign.campaign_id))
        assert any(a["action"] == "retire_series" for a in opt["actions"])
        refreshed = svc.get_campaign(campaign.campaign_id)
        assert refreshed.series[0].status == "retired"
        # Draft cancelled
        ep_ids = {e.episode_id: e for e in refreshed.series[0].episodes}
        assert ep_ids[draft.episode_id].status == "cancelled"
