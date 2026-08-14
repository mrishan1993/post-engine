from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from campaign_engine.continuity import (
    apply_episode_to_continuity,
    init_continuity,
    validate_continuity,
)
from campaign_engine.franchise import detect_franchise
from campaign_engine.narrative import (
    DEFAULT_JOURNEY,
    cross_platform_adaptations,
    decompose_episodes,
)
from campaign_engine.schemas import (
    CampaignObjective,
    CampaignOut,
    CreateCampaignRequest,
    CreateEpisodeRequest,
    CreateSeriesRequest,
    EpisodeOut,
    ExecuteEpisodeRequest,
    FranchiseOut,
    InjectTrendRequest,
    OptimizeCampaignRequest,
    RecordPerformanceRequest,
    SeriesOut,
)
from db.models import (
    Campaign,
    CampaignContent,
    CampaignDecision,
    CampaignDependency,
    CampaignEpisode,
    CampaignMetric,
    ContentSeries,
    Franchise,
)


class CampaignService:
    """Campaign & Content Portfolio — coordinates how content pieces work together."""

    def __init__(self, session: Session):
        self.session = session

    # ── Campaign CRUD ────────────────────────────────────────────────────────

    def create_campaign(self, request: CreateCampaignRequest | dict[str, Any]) -> CampaignOut:
        req = (
            request
            if isinstance(request, CreateCampaignRequest)
            else CreateCampaignRequest.model_validate(request)
        )
        objective = (
            req.objective
            if isinstance(req.objective, CampaignObjective)
            else CampaignObjective.model_validate(req.objective or {})
        )
        now = datetime.now(timezone.utc)
        continuity = init_continuity(
            character_slug=req.character_slug,
            campaign_name=req.name,
        )
        journey = {
            "stages": DEFAULT_JOURNEY,
            "mapped": {},
            "gaps": [],
        }
        kpis = {
            "primary": {"metric": "follower_growth", "target": None},
            "secondary": ["reach", "shares", "profile_visits"],
            "diagnostic": ["retention_3s", "completion", "comment_sentiment"],
        }
        row = Campaign(
            id=str(uuid4()),
            strategy_id=req.strategy_id,
            name=req.name,
            campaign_type=req.campaign_type,
            objective=objective.model_dump(),
            audience=list(req.audience),
            platforms=list(req.platforms),
            kpis=kpis,
            hypothesis=req.hypothesis
            or (
                "A recurring character-led series will generate stronger follower conversion "
                "than standalone trend content."
            ),
            priority=0.7,
            budget={"generation": 200, "content_quota": req.content_target},
            content_target=req.content_target,
            status="planned",
            character_slug=req.character_slug,
            continuity=continuity,
            journey=journey,
            start_date=now,
            end_date=now + timedelta(days=req.days),
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        self._log(
            row.id,
            "campaign_created",
            {"name": row.name, "type": row.campaign_type, "content_target": row.content_target},
            reason="strategic objective → campaign",
        )
        get_bus().publish(
            EventType.CAMPAIGN_CREATED,
            {"campaign_id": row.id, "name": row.name, "strategy_id": row.strategy_id},
            producer="campaign-engine",
        )

        if req.auto_decompose:
            series_name = req.series_name or f"{req.character_slug.replace('_', ' ').title()} Tries…"
            premise = req.series_premise or f"{req.character_slug} explores human situations"
            self._decompose(
                campaign=row,
                series_name=series_name,
                premise=premise,
                episode_count=req.episode_count,
            )
            row.status = "active"
            row.updated_at = datetime.now(timezone.utc)
            get_bus().publish(
                EventType.CAMPAIGN_STARTED,
                {"campaign_id": row.id},
                producer="campaign-engine",
            )

        self.session.flush()
        return self._campaign_out(row)

    def get_campaign(self, campaign_id: str) -> CampaignOut:
        return self._campaign_out(self._get_campaign(campaign_id))

    def pause(self, campaign_id: str) -> CampaignOut:
        row = self._get_campaign(campaign_id)
        row.status = "paused"
        row.updated_at = datetime.now(timezone.utc)
        self._log(row.id, "campaign_paused", {"status": "paused"})
        get_bus().publish(
            EventType.CAMPAIGN_PAUSED,
            {"campaign_id": row.id},
            producer="campaign-engine",
        )
        self.session.flush()
        return self._campaign_out(row)

    def resume(self, campaign_id: str) -> CampaignOut:
        row = self._get_campaign(campaign_id)
        row.status = "active"
        row.updated_at = datetime.now(timezone.utc)
        self._log(row.id, "campaign_resumed", {"status": "active"})
        get_bus().publish(
            EventType.CAMPAIGN_UPDATED,
            {"campaign_id": row.id, "status": "active"},
            producer="campaign-engine",
        )
        self.session.flush()
        return self._campaign_out(row)

    # ── Series / Episodes ────────────────────────────────────────────────────

    def create_series(self, request: CreateSeriesRequest | dict[str, Any]) -> SeriesOut:
        req = (
            request
            if isinstance(request, CreateSeriesRequest)
            else CreateSeriesRequest.model_validate(request)
        )
        campaign = self._get_campaign(req.campaign_id)
        series = ContentSeries(
            id=str(uuid4()),
            campaign_id=campaign.id,
            name=req.name,
            premise=req.premise,
            format=req.format,
            character_slug=req.character_slug or campaign.character_slug,
            publishing_cadence=req.cadence,
            status="active",
            target_episodes=req.target_episodes,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(series)
        self.session.flush()
        self._log(campaign.id, "series_created", {"series_id": series.id, "name": series.name})
        get_bus().publish(
            EventType.SERIES_CREATED,
            {"series_id": series.id, "campaign_id": campaign.id, "name": series.name},
            producer="campaign-engine",
        )
        return self._series_out(series)

    def create_episode(self, request: CreateEpisodeRequest | dict[str, Any]) -> EpisodeOut:
        req = (
            request
            if isinstance(request, CreateEpisodeRequest)
            else CreateEpisodeRequest.model_validate(request)
        )
        series = self._get_series(req.series_id)
        campaign = self._get_campaign(series.campaign_id)
        ep_num = req.episode_number
        if ep_num is None:
            existing = list(
                self.session.scalars(
                    select(CampaignEpisode).where(CampaignEpisode.series_id == series.id)
                ).all()
            )
            ep_num = max((e.episode_number for e in existing), default=0) + 1
        warnings = validate_continuity(
            campaign.continuity or {},
            proposed_premise=req.premise or "",
        )
        ep = CampaignEpisode(
            id=str(uuid4()),
            series_id=series.id,
            campaign_id=campaign.id,
            episode_number=ep_num,
            title=req.title or f"{series.name} — Ep {ep_num}",
            objective=req.objective,
            premise=req.premise,
            hook=req.hook,
            narrative_role=req.narrative_role,
            audience_role=req.audience_role,
            platform=req.platform,
            continuity_requirements=req.continuity_requirements
            or {"character_slug": campaign.character_slug, "warnings": warnings},
            cta=req.cta,
            status="draft",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(ep)
        self.session.flush()
        # Sequence dependency on previous episode
        prev = self.session.scalar(
            select(CampaignEpisode).where(
                CampaignEpisode.series_id == series.id,
                CampaignEpisode.episode_number == ep_num - 1,
            )
        )
        if prev:
            self.session.add(
                CampaignDependency(
                    id=str(uuid4()),
                    campaign_id=campaign.id,
                    source_episode_id=prev.id,
                    target_episode_id=ep.id,
                    dependency_type="sequence",
                    condition={"requires": "published_or_planned"},
                    created_at=datetime.now(timezone.utc),
                )
            )
        campaign.continuity = apply_episode_to_continuity(
            campaign.continuity or {},
            episode_number=ep_num,
            premise=req.premise,
            narrative_role=req.narrative_role,
        )
        campaign.updated_at = datetime.now(timezone.utc)
        get_bus().publish(
            EventType.EPISODE_CREATED,
            {
                "episode_id": ep.id,
                "series_id": series.id,
                "campaign_id": campaign.id,
                "episode_number": ep_num,
            },
            producer="campaign-engine",
        )
        self.session.flush()
        out = self._episode_out(ep)
        if warnings:
            # attach via continuity_requirements already
            pass
        return out

    # ── Trend injection ──────────────────────────────────────────────────────

    def inject_trend(self, request: InjectTrendRequest | dict[str, Any]) -> EpisodeOut:
        """Adapt a trend into an existing campaign episode without breaking continuity."""
        req = (
            request
            if isinstance(request, InjectTrendRequest)
            else InjectTrendRequest.model_validate(request)
        )
        campaign = self._get_campaign(req.campaign_id)
        if campaign.status in {"paused", "cancelled", "archived"}:
            raise ValueError(f"campaign is {campaign.status}")

        episode: CampaignEpisode | None = None
        if req.episode_id:
            episode = self.session.get(CampaignEpisode, req.episode_id)
        elif req.series_id:
            # Prefer mid-series escalation slot that is still draft
            candidates = list(
                self.session.scalars(
                    select(CampaignEpisode)
                    .where(
                        CampaignEpisode.series_id == req.series_id,
                        CampaignEpisode.status.in_(["draft", "planned"]),
                    )
                    .order_by(CampaignEpisode.episode_number.asc())
                ).all()
            )
            episode = next(
                (e for e in candidates if e.narrative_role in {"escalation", "reveal", "setup"}),
                candidates[0] if candidates else None,
            )
        else:
            series = self.session.scalar(
                select(ContentSeries)
                .where(ContentSeries.campaign_id == campaign.id)
                .order_by(ContentSeries.created_at.asc())
            )
            if series:
                return self.inject_trend(
                    InjectTrendRequest(
                        campaign_id=campaign.id,
                        series_id=series.id,
                        trend_id=req.trend_id,
                        viral_mechanism=req.viral_mechanism,
                        title=req.title,
                        opportunity_score=req.opportunity_score,
                    )
                )

        if not episode:
            raise ValueError("no episode available for trend injection")

        character = campaign.character_slug or "character"
        mechanism = req.viral_mechanism or "unexpected_reveal"
        adapted_title = req.title or f"{character} Tries the Trend"
        adapted_premise = (
            f"{character} encounters '{req.trend_id}' via {mechanism} — "
            f"adapted to series identity, not surface copy"
        )
        warnings = validate_continuity(campaign.continuity or {}, proposed_premise=adapted_premise)
        episode.trend_id = req.trend_id
        episode.title = adapted_title
        episode.premise = adapted_premise
        episode.hook = f"Wait until {character} tries this trend…"
        episode.narrative_role = episode.narrative_role or "escalation"
        episode.audience_role = "discovery"
        episode.continuity_requirements = {
            **(episode.continuity_requirements or {}),
            "trend_injection": True,
            "trend_id": req.trend_id,
            "viral_mechanism": mechanism,
            "preserve_series_identity": True,
            "warnings": warnings,
        }
        episode.status = "planned"
        campaign.continuity = apply_episode_to_continuity(
            campaign.continuity or {},
            episode_number=episode.episode_number,
            premise=adapted_premise,
            narrative_role=episode.narrative_role,
            facts=[f"trend_injected:{req.trend_id}"],
        )
        campaign.updated_at = datetime.now(timezone.utc)
        self._log(
            campaign.id,
            "trend_injected",
            {
                "episode_id": episode.id,
                "trend_id": req.trend_id,
                "opportunity_score": req.opportunity_score,
            },
            reason="trend advances campaign without breaking coherence",
            expected={"series_identity_preserved": True},
        )
        get_bus().publish(
            EventType.CAMPAIGN_UPDATED,
            {
                "campaign_id": campaign.id,
                "episode_id": episode.id,
                "trend_id": req.trend_id,
                "action": "trend_injected",
            },
            producer="campaign-engine",
        )
        self.session.flush()
        return self._episode_out(episode)

    # ── Performance / optimize / franchise ───────────────────────────────────

    def record_performance(
        self, request: RecordPerformanceRequest | dict[str, Any]
    ) -> EpisodeOut:
        req = (
            request
            if isinstance(request, RecordPerformanceRequest)
            else RecordPerformanceRequest.model_validate(request)
        )
        episode = self.session.get(CampaignEpisode, req.episode_id)
        if not episode:
            raise ValueError(f"episode not found: {req.episode_id}")
        perf = {
            "views": req.views,
            "shares": req.shares,
            "followers_gained": req.followers_gained,
            "retention": req.retention,
            **(req.extras or {}),
        }
        episode.performance = {k: v for k, v in perf.items() if v is not None}
        episode.status = "published"
        episode.published_at = episode.published_at or datetime.now(timezone.utc)
        for metric, value in episode.performance.items():
            if value is None:
                continue
            self.session.add(
                CampaignMetric(
                    id=str(uuid4()),
                    campaign_id=episode.campaign_id,
                    series_id=episode.series_id,
                    episode_id=episode.id,
                    metric=str(metric),
                    value=float(value),
                    period="episode",
                    source="performance",
                    created_at=datetime.now(timezone.utc),
                )
            )
        get_bus().publish(
            EventType.CAMPAIGN_PERFORMANCE_UPDATED,
            {
                "campaign_id": episode.campaign_id,
                "episode_id": episode.id,
                "performance": episode.performance,
            },
            producer="campaign-engine",
        )
        get_bus().publish(
            EventType.EPISODE_PUBLISHED,
            {"episode_id": episode.id, "campaign_id": episode.campaign_id},
            producer="campaign-engine",
        )
        self._soft_learning_handoff(episode)
        self.session.flush()
        return self._episode_out(episode)

    def optimize(self, request: OptimizeCampaignRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, OptimizeCampaignRequest)
            else OptimizeCampaignRequest.model_validate(request)
        )
        campaign = self._get_campaign(req.campaign_id)
        series_list = list(
            self.session.scalars(
                select(ContentSeries).where(ContentSeries.campaign_id == campaign.id)
            ).all()
        )
        actions: list[dict[str, Any]] = []
        franchises: list[FranchiseOut] = []

        for series in series_list:
            episodes = list(
                self.session.scalars(
                    select(CampaignEpisode)
                    .where(CampaignEpisode.series_id == series.id)
                    .order_by(CampaignEpisode.episode_number.asc())
                ).all()
            )
            published = [e for e in episodes if e.performance]
            if len(published) < 2:
                continue
            views = [float((e.performance or {}).get("views") or 0) for e in published]
            avg = sum(views) / len(views) if views else 0
            trend_up = len(views) >= 3 and views[-1] > views[0] * 1.5 and views[-1] > 1_000_000
            trend_down = len(views) >= 3 and views[-1] < views[0] * 0.4

            if req.extend_if_strong and trend_up:
                # Extend without rewriting history
                next_num = max(e.episode_number for e in episodes) + 1
                extra = self.create_episode(
                    CreateEpisodeRequest(
                        series_id=series.id,
                        episode_number=next_num,
                        title=f"{series.name} — Ep {next_num} (extended)",
                        objective="Capitalize on momentum",
                        premise=f"Extended beat after strong performance of Ep {next_num - 1}",
                        hook=f"It keeps getting better for {campaign.character_slug}",
                        narrative_role="escalation",
                        audience_role="relationship",
                        platform=episodes[0].platform if episodes else "instagram",
                    )
                )
                series.target_episodes = max(series.target_episodes, next_num)
                series.status = "validated"
                actions.append({"action": "extend_series", "episode_id": extra.episode_id})
                self._log(
                    campaign.id,
                    "series_extended",
                    {"series_id": series.id, "new_target": series.target_episodes, "avg_views": avg},
                    reason="strong episode-to-episode momentum",
                )
                get_bus().publish(
                    EventType.SERIES_EXTENDED,
                    {"series_id": series.id, "target_episodes": series.target_episodes},
                    producer="campaign-engine",
                )

            if req.retire_if_weak and trend_down:
                series.status = "retired"
                for e in episodes:
                    if e.status in {"draft", "planned"}:
                        e.status = "cancelled"
                actions.append({"action": "retire_series", "series_id": series.id, "avg_views": avg})
                self._log(
                    campaign.id,
                    "series_retired",
                    {"series_id": series.id, "views": views},
                    reason="declining episode performance / fatigue signal",
                )
                get_bus().publish(
                    EventType.SERIES_RETIRED,
                    {"series_id": series.id, "campaign_id": campaign.id},
                    producer="campaign-engine",
                )

            fr = detect_franchise(
                self.session,
                campaign_id=campaign.id,
                series=series,
                episodes=episodes,
            )
            if fr:
                franchises.append(self._franchise_out(fr))
                actions.append(
                    {"action": "franchise_detected", "franchise_id": fr.id, "confidence": float(fr.confidence or 0)}
                )

        campaign.status = "optimizing"
        campaign.updated_at = datetime.now(timezone.utc)
        get_bus().publish(
            EventType.CAMPAIGN_OPTIMIZED,
            {"campaign_id": campaign.id, "actions": [a["action"] for a in actions]},
            producer="campaign-engine",
        )
        get_bus().publish(
            EventType.CAMPAIGN_REPLANNED,
            {"campaign_id": campaign.id, "actions": actions},
            producer="campaign-engine",
        )
        self.session.flush()
        return {
            "campaign_id": campaign.id,
            "status": campaign.status,
            "actions": actions,
            "franchises": [f.model_dump(mode="json") for f in franchises],
        }

    def approve_franchise(self, franchise_id: str) -> FranchiseOut:
        row = self.session.get(Franchise, franchise_id)
        if not row:
            raise ValueError(f"franchise not found: {franchise_id}")
        row.status = "approved"
        if row.series_id:
            series = self.session.get(ContentSeries, row.series_id)
            if series:
                series.status = "franchise"
        self._log(
            row.campaign_id,
            "franchise_approved",
            {"franchise_id": row.id, "series_id": row.series_id},
            reason="human approval (V1 Level 1–2)",
        )
        get_bus().publish(
            EventType.FRANCHISE_APPROVED,
            {"franchise_id": row.id, "series_id": row.series_id},
            producer="campaign-engine",
        )
        self.session.flush()
        return self._franchise_out(row)

    # ── Execute → Strategy + Orchestration ───────────────────────────────────

    def execute_episode(
        self, request: ExecuteEpisodeRequest | dict[str, Any]
    ) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, ExecuteEpisodeRequest)
            else ExecuteEpisodeRequest.model_validate(request)
        )
        episode = self.session.get(CampaignEpisode, req.episode_id)
        if not episode:
            raise ValueError(f"episode not found: {req.episode_id}")
        campaign = self._get_campaign(episode.campaign_id)
        series = self._get_series(episode.series_id)

        # Dependency check: prior sequence episode should not be cancelled
        deps = list(
            self.session.scalars(
                select(CampaignDependency).where(
                    CampaignDependency.target_episode_id == episode.id
                )
            ).all()
        )
        for dep in deps:
            src = self.session.get(CampaignEpisode, dep.source_episode_id)
            if src and src.status == "cancelled":
                raise ValueError(f"dependency unmet: episode {src.episode_number} cancelled")

        strategy_opp_id = None
        if req.push_to_strategy and campaign.strategy_id:
            try:
                from strategy_engine.schemas import IngestOpportunityRequest
                from strategy_engine.service import StrategyService

                opp = StrategyService(self.session).ingest_opportunity(
                    IngestOpportunityRequest(
                        strategy_id=campaign.strategy_id,
                        source="campaign",
                        title=episode.title or series.name,
                        pillar="character",
                        platform=episode.platform,
                        trend_id=episode.trend_id,
                        payload={
                            "campaign_id": campaign.id,
                            "series_id": series.id,
                            "episode_id": episode.id,
                            "episode_number": episode.episode_number,
                            "narrative_role": episode.narrative_role,
                            "audience_role": episode.audience_role,
                            "opportunity_score": 0.75,
                            "viral_mechanism": (episode.continuity_requirements or {}).get(
                                "viral_mechanism"
                            )
                            or "character_series",
                            "lineage": self.lineage(campaign.id, episode_id=episode.id),
                        },
                    )
                )
                strategy_opp_id = opp.opportunity_id
                episode.strategy_opportunity_id = strategy_opp_id
            except Exception:  # noqa: BLE001
                strategy_opp_id = None

        from orchestration_engine.schemas import CreateJobRequest, TrendOpportunityIn
        from orchestration_engine.service import OrchestrationService

        trend_id = episode.trend_id or f"campaign_{campaign.id[:8]}_ep{episode.episode_number}"
        job = OrchestrationService(self.session).create_job(
            CreateJobRequest(
                opportunity=TrendOpportunityIn(
                    trend_id=trend_id,
                    platform=episode.platform,
                    trend_stage="campaign" if not episode.trend_id else "accelerating",
                    velocity_score=0.7,
                    freshness_score=0.75,
                    saturation_score=0.25,
                    opportunity_score=0.8,
                    viral_mechanism=(episode.continuity_requirements or {}).get("viral_mechanism")
                    or "character_series",
                    title=episode.title,
                    audience=list(campaign.audience or ["gen_z"]),
                    raw={
                        "campaign_id": campaign.id,
                        "series_id": series.id,
                        "episode_id": episode.id,
                        "narrative_role": episode.narrative_role,
                        "audience_role": episode.audience_role,
                        "hook": episode.hook,
                        "premise": episode.premise,
                        "lineage": self.lineage(campaign.id, episode_id=episode.id),
                    },
                ),
                character_slug=campaign.character_slug or "ghost_kid",
                platform=episode.platform,
                mode=req.orchestration_mode,  # type: ignore[arg-type]
                process=True,
                run_pipeline=req.run_pipeline,
            )
        )
        episode.orchestration_job_id = job.job_id
        episode.status = "production"
        # Cross-platform content map
        for adapt in cross_platform_adaptations(
            {"title": episode.title, "hook": episode.hook},
            list(campaign.platforms or [episode.platform]),
        ):
            self.session.add(
                CampaignContent(
                    id=str(uuid4()),
                    campaign_id=campaign.id,
                    episode_id=episode.id,
                    content_id=None,
                    role="platform_adaptation",
                    platform=adapt["platform"],
                    sequence_position=episode.episode_number,
                    status="planned",
                    meta=adapt,
                    created_at=datetime.now(timezone.utc),
                )
            )
        self._log(
            campaign.id,
            "episode_execution_requested",
            {
                "episode_id": episode.id,
                "orchestration_job_id": job.job_id,
                "strategy_opportunity_id": strategy_opp_id,
            },
            reason="campaign episode → orchestrator",
        )
        get_bus().publish(
            EventType.EPISODE_EXECUTION_REQUESTED,
            {
                "episode_id": episode.id,
                "campaign_id": campaign.id,
                "orchestration_job_id": job.job_id,
                "strategy_opportunity_id": strategy_opp_id,
            },
            producer="campaign-engine",
        )
        self.session.flush()
        return {
            "episode_id": episode.id,
            "campaign_id": campaign.id,
            "series_id": series.id,
            "orchestration_job_id": job.job_id,
            "orchestration_status": job.status,
            "strategy_opportunity_id": strategy_opp_id,
            "lineage": self.lineage(campaign.id, episode_id=episode.id),
        }

    def lineage(self, campaign_id: str, *, episode_id: str | None = None) -> dict[str, Any]:
        campaign = self._get_campaign(campaign_id)
        chain: dict[str, Any] = {
            "business_objective": (campaign.objective or {}).get("primary"),
            "strategy_id": campaign.strategy_id,
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "hypothesis": campaign.hypothesis,
        }
        if episode_id:
            ep = self.session.get(CampaignEpisode, episode_id)
            if ep:
                series = self.session.get(ContentSeries, ep.series_id)
                chain.update(
                    {
                        "series_id": ep.series_id,
                        "series_name": series.name if series else None,
                        "episode_id": ep.id,
                        "episode_number": ep.episode_number,
                        "narrative_role": ep.narrative_role,
                        "audience_role": ep.audience_role,
                        "content_id": None,
                        "orchestration_job_id": ep.orchestration_job_id,
                        "performance": ep.performance,
                    }
                )
        return chain

    def portfolio(self, campaign_id: str | None = None) -> dict[str, Any]:
        q = select(Campaign)
        if campaign_id:
            q = q.where(Campaign.id == campaign_id)
        campaigns = list(self.session.scalars(q).all())
        return {
            "campaigns": [
                {
                    "campaign_id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "content_target": c.content_target,
                    "priority": float(c.priority or 0),
                    "allocation": {
                        "campaign_driven": 0.35,
                        "trend_reactive": 0.25,
                        "evergreen": 0.15,
                        "series": 0.15,
                        "experiments": 0.10,
                    },
                }
                for c in campaigns
            ]
        }

    def decisions(self, campaign_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        self._get_campaign(campaign_id)
        rows = list(
            self.session.scalars(
                select(CampaignDecision)
                .where(CampaignDecision.campaign_id == campaign_id)
                .order_by(CampaignDecision.created_at.desc())
                .limit(limit)
            ).all()
        )
        return [
            {
                "id": r.id,
                "decision_type": r.decision_type,
                "decision": r.decision,
                "reason": r.reason,
                "expected_outcome": r.expected_outcome,
                "model_version": r.model_version,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    # ── Internals ────────────────────────────────────────────────────────────

    def _decompose(
        self,
        *,
        campaign: Campaign,
        series_name: str,
        premise: str,
        episode_count: int,
    ) -> ContentSeries:
        series = ContentSeries(
            id=str(uuid4()),
            campaign_id=campaign.id,
            name=series_name,
            premise=premise,
            format="reel",
            character_slug=campaign.character_slug,
            narrative_rules={"preserve_character": True, "allow_trend_injection": True},
            visual_rules={"consistent_character": True},
            episode_template={"hook_required": True, "cta_required": True},
            publishing_cadence={"per_week": 2},
            platform_strategy={"primary": (campaign.platforms or ["instagram"])[0]},
            success_metrics={"views_lift": 1.5, "follower_conversion": True},
            status="active",
            target_episodes=episode_count,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(series)
        self.session.flush()
        get_bus().publish(
            EventType.SERIES_CREATED,
            {"series_id": series.id, "campaign_id": campaign.id, "name": series.name},
            producer="campaign-engine",
        )

        skeletons = decompose_episodes(
            count=episode_count,
            character_slug=campaign.character_slug or "character",
            series_name=series_name,
            premise=premise,
            platforms=list(campaign.platforms or ["instagram"]),
        )
        prev_id: str | None = None
        journey_map: dict[str, list[str]] = {}
        for sk in skeletons:
            ep = CampaignEpisode(
                id=str(uuid4()),
                series_id=series.id,
                campaign_id=campaign.id,
                episode_number=sk["episode_number"],
                title=sk["title"],
                objective=sk["objective"],
                premise=sk["premise"],
                hook=sk["hook"],
                narrative_role=sk["narrative_role"],
                audience_role=sk["audience_role"],
                platform=sk["platform"],
                continuity_requirements=sk["continuity_requirements"],
                cta=sk["cta"],
                status="planned",
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(ep)
            self.session.flush()
            journey_map.setdefault(sk["audience_role"], []).append(ep.id)
            if prev_id:
                self.session.add(
                    CampaignDependency(
                        id=str(uuid4()),
                        campaign_id=campaign.id,
                        source_episode_id=prev_id,
                        target_episode_id=ep.id,
                        dependency_type="sequence",
                        condition={"requires": "prior_episode"},
                        created_at=datetime.now(timezone.utc),
                    )
                )
            campaign.continuity = apply_episode_to_continuity(
                campaign.continuity or {},
                episode_number=ep.episode_number,
                premise=ep.premise,
                narrative_role=ep.narrative_role,
            )
            get_bus().publish(
                EventType.EPISODE_CREATED,
                {
                    "episode_id": ep.id,
                    "series_id": series.id,
                    "campaign_id": campaign.id,
                    "episode_number": ep.episode_number,
                },
                producer="campaign-engine",
            )
            # Cross-platform planned content
            for adapt in cross_platform_adaptations(
                {"title": ep.title, "hook": ep.hook},
                list(campaign.platforms or [ep.platform]),
            ):
                self.session.add(
                    CampaignContent(
                        id=str(uuid4()),
                        campaign_id=campaign.id,
                        episode_id=ep.id,
                        role="platform_adaptation",
                        platform=adapt["platform"],
                        sequence_position=ep.episode_number,
                        status="planned",
                        meta=adapt,
                        created_at=datetime.now(timezone.utc),
                    )
                )
            prev_id = ep.id

        journey = dict(campaign.journey or {})
        journey["mapped"] = journey_map
        # Gap detection
        expected = {"discovery", "curiosity", "relationship", "community"}
        present = set(journey_map.keys())
        journey["gaps"] = sorted(expected - present)
        campaign.journey = journey
        self._log(
            campaign.id,
            "campaign_decomposed",
            {
                "series_id": series.id,
                "episodes": episode_count,
                "journey_gaps": journey["gaps"],
            },
            reason="campaign → series → episodes",
        )
        return series

    def _soft_learning_handoff(self, episode: CampaignEpisode) -> None:
        try:
            from learning_engine.service import LearningService

            # Best-effort observation; LearningService APIs vary — use observe if present
            svc = LearningService(self.session)
            if hasattr(svc, "ingest_observation"):
                svc.ingest_observation(  # type: ignore[attr-defined]
                    {
                        "source": "campaign",
                        "campaign_id": episode.campaign_id,
                        "episode_id": episode.id,
                        "performance": episode.performance,
                    }
                )
            elif hasattr(svc, "observe"):
                svc.observe(  # type: ignore[attr-defined]
                    {
                        "source": "campaign",
                        "campaign_id": episode.campaign_id,
                        "episode_id": episode.id,
                        "performance": episode.performance,
                    }
                )
        except Exception:  # noqa: BLE001
            pass

    def _log(
        self,
        campaign_id: str | None,
        decision_type: str,
        decision: dict[str, Any],
        *,
        reason: str | None = None,
        expected: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            CampaignDecision(
                id=str(uuid4()),
                campaign_id=campaign_id,
                decision_type=decision_type,
                decision=decision,
                reason=reason,
                expected_outcome=expected,
                model_version="campaign_v1",
                created_at=datetime.now(timezone.utc),
            )
        )

    def _get_campaign(self, campaign_id: str) -> Campaign:
        row = self.session.get(Campaign, campaign_id)
        if not row:
            raise ValueError(f"campaign not found: {campaign_id}")
        return row

    def _get_series(self, series_id: str) -> ContentSeries:
        row = self.session.get(ContentSeries, series_id)
        if not row:
            raise ValueError(f"series not found: {series_id}")
        return row

    def _episode_out(self, ep: CampaignEpisode) -> EpisodeOut:
        return EpisodeOut(
            episode_id=ep.id,
            series_id=ep.series_id,
            campaign_id=ep.campaign_id,
            episode_number=ep.episode_number,
            title=ep.title,
            objective=ep.objective,
            premise=ep.premise,
            hook=ep.hook,
            narrative_role=ep.narrative_role,
            audience_role=ep.audience_role,
            platform=ep.platform,
            trend_id=ep.trend_id,
            status=ep.status,
            performance=ep.performance,
            orchestration_job_id=ep.orchestration_job_id,
            continuity_requirements=ep.continuity_requirements or {},
        )

    def _series_out(self, series: ContentSeries) -> SeriesOut:
        eps = list(
            self.session.scalars(
                select(CampaignEpisode)
                .where(CampaignEpisode.series_id == series.id)
                .order_by(CampaignEpisode.episode_number.asc())
            ).all()
        )
        return SeriesOut(
            series_id=series.id,
            campaign_id=series.campaign_id,
            name=series.name,
            premise=series.premise,
            status=series.status,
            target_episodes=series.target_episodes,
            episodes=[self._episode_out(e) for e in eps],
        )

    def _franchise_out(self, fr: Franchise) -> FranchiseOut:
        return FranchiseOut(
            franchise_id=fr.id,
            campaign_id=fr.campaign_id,
            series_id=fr.series_id,
            name=fr.name,
            status=fr.status,
            confidence=float(fr.confidence) if fr.confidence is not None else None,
            performance_basis=fr.performance_basis or {},
        )

    def _campaign_out(self, row: Campaign) -> CampaignOut:
        series = list(
            self.session.scalars(
                select(ContentSeries).where(ContentSeries.campaign_id == row.id)
            ).all()
        )
        return CampaignOut(
            campaign_id=row.id,
            strategy_id=row.strategy_id,
            name=row.name,
            campaign_type=row.campaign_type,
            objective=row.objective or {},
            audience=list(row.audience or []),
            platforms=list(row.platforms or []),
            status=row.status,
            priority=float(row.priority or 0),
            content_target=row.content_target,
            character_slug=row.character_slug,
            hypothesis=row.hypothesis,
            continuity=row.continuity or {},
            journey=row.journey or {},
            series=[self._series_out(s) for s in series],
            warnings=list((row.journey or {}).get("gaps") or []),
        )
