from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from strategy_engine.planner import build_plan, plan_to_out, replan_with_urgent_trend
from strategy_engine.schemas import (
    CreatePlanRequest,
    CreateStrategyRequest,
    ExecuteRequest,
    IngestOpportunityRequest,
    OpportunityOut,
    PlanOut,
    ReplanRequest,
    StrategyOut,
    StrategyProfile,
)
from strategy_engine.scoring import estimate_expiration, score_opportunity
from db.models import (
    ContentPlan,
    ContentPlanItem,
    ContentStrategy,
    StrategyDecisionLog,
    StrategyOpportunity,
)


class StrategyService:
    """Content Strategy & Planning — portfolio brain above Trend + Orchestration."""

    def __init__(self, session: Session):
        self.session = session

    def create_strategy(self, request: CreateStrategyRequest | dict[str, Any]) -> StrategyOut:
        req = (
            request
            if isinstance(request, CreateStrategyRequest)
            else CreateStrategyRequest.model_validate(request)
        )
        profile = (
            req.profile
            if isinstance(req.profile, StrategyProfile)
            else StrategyProfile.model_validate(req.profile or {})
        )
        row = ContentStrategy(
            id=str(uuid4()),
            name=req.name,
            character_slug=req.character_slug,
            profile=profile.model_dump(),
            status="active",
            autonomy=req.autonomy,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        self._log(row.id, None, "strategy_created", {"name": row.name, "autonomy": row.autonomy})
        get_bus().publish(
            EventType.STRATEGY_CREATED,
            {"strategy_id": row.id, "name": row.name},
            producer="strategy-engine",
        )
        return self._strategy_out(row)

    def get_strategy(self, strategy_id: str) -> StrategyOut:
        return self._strategy_out(self._get_strategy(strategy_id))

    def update_strategy(self, strategy_id: str, patch: dict[str, Any]) -> StrategyOut:
        row = self._get_strategy(strategy_id)
        if "profile" in patch:
            profile = StrategyProfile.model_validate(patch["profile"])
            row.profile = profile.model_dump()
            row.version = int(row.version or 1) + 1
        if "status" in patch:
            row.status = patch["status"]
        if "autonomy" in patch:
            row.autonomy = patch["autonomy"]
        if "name" in patch:
            row.name = patch["name"]
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self._log(row.id, None, "strategy_updated", patch)
        get_bus().publish(
            EventType.STRATEGY_UPDATED,
            {"strategy_id": row.id, "version": row.version},
            producer="strategy-engine",
        )
        return self._strategy_out(row)

    def pause(self, strategy_id: str) -> StrategyOut:
        return self.update_strategy(strategy_id, {"status": "paused"})

    def ingest_opportunity(
        self, request: IngestOpportunityRequest | dict[str, Any]
    ) -> OpportunityOut:
        req = (
            request
            if isinstance(request, IngestOpportunityRequest)
            else IngestOpportunityRequest.model_validate(request)
        )
        strategy = self._get_strategy(req.strategy_id)
        if strategy.status == "paused":
            raise ValueError("strategy is paused")
        profile = StrategyProfile.model_validate(strategy.profile)

        learning_boost = 0.0
        try:
            from learning_engine.service import LearningService

            brief = LearningService(self.session).brief(
                character=strategy.character_slug,
                platform=req.platform,
                persist=False,
            )
            if (brief.get("confidence") or 0) > 0.5:
                learning_boost = 0.1
        except Exception:  # noqa: BLE001
            pass

        pillar = req.pillar or (
            "trend"
            if req.source == "trend"
            else "experiment"
            if req.source == "experiment"
            else "evergreen"
        )
        payload = dict(req.payload or {})
        if req.title:
            payload.setdefault("title", req.title)
        if req.expiration_hours is not None:
            payload["expiration_hours"] = req.expiration_hours

        score, breakdown, priority = score_opportunity(
            profile=profile,
            source=req.source,
            pillar=pillar,
            platform=req.platform,
            payload=payload,
            learning_boost=learning_boost,
        )

        status = "evaluating"
        if req.auto_accept:
            # Poor strategic fit / brand violation / low score → reject
            if (
                breakdown.get("strategic_fit", 1) < 0.25
                or score < 0.35
                or breakdown.get("strategic_fit", 1) <= 0.1
            ):
                status = "rejected"
            else:
                status = "accepted"

        opp = StrategyOpportunity(
            id=str(uuid4()),
            strategy_id=strategy.id,
            source=req.source,
            title=req.title or payload.get("title"),
            objective=req.objective or (profile.content_objectives[0] if profile.content_objectives else None),
            audience=req.audience
            or (profile.target_audiences[0].id if profile.target_audiences else None),
            pillar=pillar,
            platform=req.platform,
            format=req.format,
            priority=priority,
            strategic_score=score,
            score_breakdown=breakdown,
            expected_impact=breakdown.get("expected_impact"),
            effort=breakdown.get("effort"),
            payload=payload,
            status=status,
            expiration_at=estimate_expiration(req.source, payload),
            trend_id=req.trend_id or payload.get("trend_id"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(opp)
        self.session.flush()

        get_bus().publish(
            EventType.OPPORTUNITY_RECEIVED,
            {"opportunity_id": opp.id, "strategy_id": strategy.id, "source": opp.source},
            producer="strategy-engine",
        )
        get_bus().publish(
            EventType.OPPORTUNITY_SCORED,
            {
                "opportunity_id": opp.id,
                "score": score,
                "priority": priority,
                "breakdown": breakdown,
            },
            producer="strategy-engine",
        )
        evt = EventType.OPPORTUNITY_ACCEPTED if status == "accepted" else EventType.OPPORTUNITY_REJECTED
        if status == "accepted":
            get_bus().publish(
                evt,
                {"opportunity_id": opp.id, "status": status},
                producer="strategy-engine",
            )
        elif status == "rejected":
            get_bus().publish(
                evt,
                {"opportunity_id": opp.id, "status": status, "reason": "low_strategic_fit_or_score"},
                producer="strategy-engine",
            )
        self._log(
            strategy.id,
            None,
            "opportunity_scored",
            {"opportunity_id": opp.id, "score": score, "status": status, "priority": priority},
            reason=f"source={req.source} pillar={pillar}",
        )
        return self._opp_out(opp)

    def list_opportunities(
        self,
        strategy_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[OpportunityOut]:
        stmt = (
            select(StrategyOpportunity)
            .where(StrategyOpportunity.strategy_id == self._get_strategy(strategy_id).id)
            .order_by(StrategyOpportunity.strategic_score.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(StrategyOpportunity.status == status)
        return [self._opp_out(o) for o in self.session.scalars(stmt).all()]

    def create_plan(self, request: CreatePlanRequest | dict[str, Any]) -> PlanOut:
        req = (
            request
            if isinstance(request, CreatePlanRequest)
            else CreatePlanRequest.model_validate(request)
        )
        strategy = self._get_strategy(req.strategy_id)
        profile = StrategyProfile.model_validate(strategy.profile)
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=req.days)

        opps = list(
            self.session.scalars(
                select(StrategyOpportunity).where(
                    StrategyOpportunity.strategy_id == strategy.id,
                    StrategyOpportunity.status.in_(
                        ["accepted", "planned", "deferred", "detected", "evaluating"]
                    ),
                )
            ).all()
        )
        learning_brief = None
        try:
            from learning_engine.service import LearningService

            learning_brief = LearningService(self.session).brief(
                character=strategy.character_slug,
                platform="instagram",
                persist=False,
            ).get("brief")
        except Exception:  # noqa: BLE001
            pass

        prev = self.session.scalar(
            select(ContentPlan)
            .where(ContentPlan.strategy_id == strategy.id, ContentPlan.status == "active")
            .order_by(ContentPlan.created_at.desc())
        )
        plan, _items, warnings, debt = build_plan(
            self.session,
            strategy_id=strategy.id,
            profile=profile,
            opportunities=opps,
            period_start=start,
            period_end=end,
            learning_brief=learning_brief,
            previous_plan=prev,
        )
        self._log(
            strategy.id,
            plan.id,
            "plan_created",
            {"plan_id": plan.id, "slots": len(_items), "warnings": warnings},
        )
        return plan_to_out(self.session, plan, warnings=warnings, debt=debt)

    def get_plan(self, plan_id: str) -> PlanOut:
        plan = self._get_plan(plan_id)
        return plan_to_out(self.session, plan)

    def calendar(self, strategy_id: str, *, plan_id: str | None = None) -> list[dict[str, Any]]:
        if plan_id:
            plan = self._get_plan(plan_id)
        else:
            plan = self.session.scalar(
                select(ContentPlan)
                .where(
                    ContentPlan.strategy_id == self._get_strategy(strategy_id).id,
                    ContentPlan.status == "active",
                )
                .order_by(ContentPlan.created_at.desc())
            )
            if not plan:
                return []
        out = plan_to_out(self.session, plan)
        return [
            {
                "scheduled_at": it.scheduled_at.isoformat() if it.scheduled_at else None,
                "platform": it.platform,
                "pillar": it.pillar,
                "type": it.content_type,
                "priority": it.priority,
                "title": it.title,
                "status": it.status,
                "opportunity_id": it.opportunity_id,
                "item_id": it.item_id,
            }
            for it in out.items
            if it.status in {"planned", "scheduled"}
        ]

    def replan(self, request: ReplanRequest | dict[str, Any]) -> PlanOut:
        req = (
            request if isinstance(request, ReplanRequest) else ReplanRequest.model_validate(request)
        )
        plan = self._get_plan(req.plan_id)
        strategy = self._get_strategy(plan.strategy_id)
        profile = StrategyProfile.model_validate(strategy.profile)

        if req.force_trend_id:
            urgent = self.session.scalar(
                select(StrategyOpportunity).where(
                    StrategyOpportunity.strategy_id == strategy.id,
                    StrategyOpportunity.trend_id == req.force_trend_id,
                )
            )
            if not urgent:
                # try by id
                urgent = self.session.get(StrategyOpportunity, req.force_trend_id)
            if urgent:
                _, notes = replan_with_urgent_trend(
                    self.session,
                    plan=plan,
                    profile=profile,
                    opportunities=[],
                    urgent=urgent,
                )
                out = plan_to_out(self.session, plan, warnings=notes)
                return out

        # Full rebuild
        return self.create_plan(CreatePlanRequest(strategy_id=strategy.id, days=7))

    def execute(self, request: ExecuteRequest | dict[str, Any]) -> list[dict[str, Any]]:
        """Submit top scheduled opportunities to Trend-to-Reel Orchestrator."""
        req = (
            request if isinstance(request, ExecuteRequest) else ExecuteRequest.model_validate(request)
        )
        strategy = self._get_strategy(req.strategy_id)
        if strategy.status == "paused":
            raise ValueError("strategy is paused")

        if req.plan_id:
            plan = self._get_plan(req.plan_id)
        else:
            plan = self.session.scalar(
                select(ContentPlan)
                .where(ContentPlan.strategy_id == strategy.id, ContentPlan.status == "active")
                .order_by(ContentPlan.created_at.desc())
            )
            if not plan:
                raise ValueError("no active plan")

        items = list(
            self.session.scalars(
                select(ContentPlanItem)
                .where(
                    ContentPlanItem.plan_id == plan.id,
                    ContentPlanItem.status.in_(["scheduled", "planned"]),
                )
                .order_by(ContentPlanItem.scheduled_at.asc())
            ).all()
        )[: req.max_jobs]

        results: list[dict[str, Any]] = []
        from orchestration_engine.schemas import CreateJobRequest, TrendOpportunityIn
        from orchestration_engine.service import OrchestrationService

        orch = OrchestrationService(self.session)
        for it in items:
            opp = self.session.get(StrategyOpportunity, it.opportunity_id) if it.opportunity_id else None
            if not opp:
                continue
            payload = dict(opp.payload or {})
            trend = TrendOpportunityIn(
                trend_id=opp.trend_id or opp.id,
                platform=opp.platform,
                trend_stage=str(payload.get("trend_stage") or "accelerating"),
                velocity_score=float(payload.get("velocity_score") or opp.strategic_score or 0.7),
                freshness_score=float(payload.get("freshness_score") or 0.7),
                saturation_score=float(payload.get("saturation_score") or 0.3),
                opportunity_score=float(opp.strategic_score or 0.7),
                viral_mechanism=payload.get("viral_mechanism") or opp.pillar,
                title=opp.title,
                audience=[opp.audience] if opp.audience else ["gen_z"],
            )
            job = orch.create_job(
                CreateJobRequest(
                    opportunity=trend,
                    character_slug=strategy.character_slug or "ghost_kid",
                    mode=req.orchestration_mode,  # type: ignore[arg-type]
                    process=True,
                    run_pipeline=req.run_pipeline,
                )
            )
            it.status = "production"
            opp.status = "production"
            opp.orchestration_job_id = job.job_id
            results.append(
                {
                    "item_id": it.id,
                    "opportunity_id": opp.id,
                    "orchestration_job_id": job.job_id,
                    "orchestration_status": job.status,
                }
            )
            get_bus().publish(
                EventType.CONTENT_EXECUTION_REQUESTED,
                {
                    "strategy_id": strategy.id,
                    "plan_id": plan.id,
                    "opportunity_id": opp.id,
                    "orchestration_job_id": job.job_id,
                },
                producer="strategy-engine",
            )
        self.session.flush()
        return results

    def decisions(self, strategy_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        sid = self._get_strategy(strategy_id).id
        rows = list(
            self.session.scalars(
                select(StrategyDecisionLog)
                .where(StrategyDecisionLog.strategy_id == sid)
                .order_by(StrategyDecisionLog.created_at.desc())
                .limit(limit)
            ).all()
        )
        return [
            {
                "id": r.id,
                "plan_id": r.plan_id,
                "decision_type": r.decision_type,
                "decision": r.decision,
                "reason": r.reason,
                "expected_outcome": r.expected_outcome,
                "model_version": r.model_version,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def health(self, strategy_id: str) -> dict[str, Any]:
        strategy = self._get_strategy(strategy_id)
        profile = StrategyProfile.model_validate(strategy.profile)
        plan = self.session.scalar(
            select(ContentPlan)
            .where(ContentPlan.strategy_id == strategy.id, ContentPlan.status == "active")
            .order_by(ContentPlan.created_at.desc())
        )
        opps = list(
            self.session.scalars(
                select(StrategyOpportunity).where(StrategyOpportunity.strategy_id == strategy.id)
            ).all()
        )
        return {
            "strategy_id": strategy.id,
            "status": strategy.status,
            "opportunity_counts": _count_by(opps, "status"),
            "active_plan_id": plan.id if plan else None,
            "capacity": profile.capacity,
            "content_mix": profile.content_mix,
            "note": "Optimize for portfolio value, not raw views",
        }

    def _get_strategy(self, strategy_id: str) -> ContentStrategy:
        row = self.session.get(ContentStrategy, strategy_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(ContentStrategy).where(ContentStrategy.id.startswith(strategy_id))
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("strategy not found")
        return rows[0]

    def _get_plan(self, plan_id: str) -> ContentPlan:
        row = self.session.get(ContentPlan, plan_id)
        if row:
            return row
        rows = list(
            self.session.scalars(select(ContentPlan).where(ContentPlan.id.startswith(plan_id))).all()
        )
        if len(rows) != 1:
            raise ValueError("plan not found")
        return rows[0]

    def _strategy_out(self, row: ContentStrategy) -> StrategyOut:
        return StrategyOut(
            strategy_id=row.id,
            name=row.name,
            character_slug=row.character_slug,
            profile=StrategyProfile.model_validate(row.profile),
            status=row.status,
            autonomy=row.autonomy,
            version=int(row.version or 1),
        )

    def _opp_out(self, opp: StrategyOpportunity) -> OpportunityOut:
        return OpportunityOut(
            opportunity_id=opp.id,
            strategy_id=opp.strategy_id,
            source=opp.source,
            title=opp.title,
            pillar=opp.pillar,
            platform=opp.platform,
            priority=opp.priority,
            strategic_score=float(opp.strategic_score) if opp.strategic_score is not None else None,
            score_breakdown={k: float(v) for k, v in (opp.score_breakdown or {}).items()},
            status=opp.status,
            expiration_at=opp.expiration_at,
            trend_id=opp.trend_id,
        )

    def _log(
        self,
        strategy_id: str | None,
        plan_id: str | None,
        decision_type: str,
        decision: dict[str, Any],
        *,
        reason: str | None = None,
        expected_outcome: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            StrategyDecisionLog(
                id=str(uuid4()),
                strategy_id=strategy_id,
                plan_id=plan_id,
                decision_type=decision_type,
                decision=decision,
                reason=reason,
                expected_outcome=expected_outcome,
                model_version="strategy_planner_v1",
            )
        )
        self.session.flush()


def _count_by(rows: list[Any], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = getattr(r, attr) or "unknown"
        out[k] = out.get(k, 0) + 1
    return out
