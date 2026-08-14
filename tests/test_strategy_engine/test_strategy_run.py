from __future__ import annotations

from amp_platform.events import EventType, get_bus, reset_bus
from db.session import get_session
from strategy_engine.portfolio import capacity_slots, detect_content_debt, detect_saturation
from strategy_engine.schemas import (
    CreatePlanRequest,
    CreateStrategyRequest,
    ExecuteRequest,
    IngestOpportunityRequest,
    ReplanRequest,
    StrategyProfile,
)
from strategy_engine.scoring import score_opportunity
from strategy_engine.service import StrategyService


def test_score_prefers_strategic_fit_not_raw_virality() -> None:
    profile = StrategyProfile()
    high_viral_bad_fit, br, _ = score_opportunity(
        profile=profile,
        source="trend",
        pillar="trend",
        platform="instagram",
        payload={
            "opportunity_score": 0.99,
            "velocity_score": 0.99,
            "freshness_score": 0.9,
            "saturation_score": 0.1,
            "title": "banned-topic spam",
            "risk": 0.9,
        },
    )
    # Mark forbidden
    profile.brand_constraints = {"forbidden_topics": ["banned-topic"]}
    scored, br2, _ = score_opportunity(
        profile=profile,
        source="trend",
        pillar="trend",
        platform="instagram",
        payload={
            "opportunity_score": 0.99,
            "velocity_score": 0.99,
            "freshness_score": 0.9,
            "saturation_score": 0.1,
            "title": "banned-topic spam",
        },
    )
    assert br2["strategic_fit"] < br["strategic_fit"]
    assert scored < high_viral_bad_fit


def test_capacity_and_debt_helpers() -> None:
    profile = StrategyProfile()
    assert capacity_slots(profile, 7) <= int(profile.capacity["reels_per_week"])
    debt = detect_content_debt(profile, ["trend", "trend", "trend", "trend"], horizon_slots=10)
    assert "education" in debt or "evergreen" in debt or "character" in debt
    warns = detect_saturation(
        ["POV"] * 7,
        ["trend"] * 7,
        ["reel"] * 7,
        max_same_hook_in_10=3,
    )
    assert warns


def test_strategy_plan_calendar_replan_execute(db_url: str) -> None:
    reset_bus()
    with get_session(db_url) as session:
        svc = StrategyService(session)
        strategy = svc.create_strategy(
            CreateStrategyRequest(
                name="growth",
                character_slug="ghost_kid",
                profile=StrategyProfile(
                    capacity={"reels_per_week": 10, "reels_per_day": 2},
                    cadence={"posts_per_day": 2, "posts_per_week": 10},
                ),
            )
        )
        # Rejectable: forbidden + auto
        bad = svc.ingest_opportunity(
            IngestOpportunityRequest(
                strategy_id=strategy.strategy_id,
                source="trend",
                title="casino spam giveaway",
                payload={
                    "opportunity_score": 0.95,
                    "velocity_score": 0.95,
                    "freshness_score": 0.9,
                    "saturation_score": 0.1,
                },
            )
        )
        # Update strategy to forbid casino
        svc.update_strategy(
            strategy.strategy_id,
            {
                "profile": {
                    **strategy.profile.model_dump(),
                    "brand_constraints": {"forbidden_topics": ["casino"], "max_same_hook_in_10": 3},
                }
            },
        )
        bad2 = svc.ingest_opportunity(
            IngestOpportunityRequest(
                strategy_id=strategy.strategy_id,
                source="trend",
                title="casino spam giveaway",
                payload={
                    "opportunity_score": 0.95,
                    "velocity_score": 0.95,
                    "freshness_score": 0.9,
                    "saturation_score": 0.1,
                },
            )
        )
        assert bad2.status == "rejected"

        # Seed portfolio
        urgent = svc.ingest_opportunity(
            IngestOpportunityRequest(
                strategy_id=strategy.strategy_id,
                source="trend",
                title="Unexpected reveal accelerating",
                pillar="trend",
                trend_id="trend_urgent_1",
                expiration_hours=10,
                payload={
                    "opportunity_score": 0.92,
                    "velocity_score": 0.95,
                    "freshness_score": 0.9,
                    "saturation_score": 0.15,
                    "viral_mechanism": "unexpected_reveal",
                    "trend_stage": "accelerating",
                },
            )
        )
        assert urgent.status == "accepted"
        assert urgent.priority in {"P0", "P1", "P2"}

        evergreen = svc.ingest_opportunity(
            IngestOpportunityRequest(
                strategy_id=strategy.strategy_id,
                source="evergreen",
                title="Evergreen character beat",
                pillar="evergreen",
                payload={"opportunity_score": 0.55, "freshness_score": 0.5, "saturation_score": 0.1},
            )
        )
        svc.ingest_opportunity(
            IngestOpportunityRequest(
                strategy_id=strategy.strategy_id,
                source="evergreen",
                title="Education tip",
                pillar="education",
                payload={"opportunity_score": 0.5, "freshness_score": 0.5},
            )
        )
        svc.ingest_opportunity(
            IngestOpportunityRequest(
                strategy_id=strategy.strategy_id,
                source="experiment",
                title="Hook length experiment",
                pillar="experiment",
                payload={"opportunity_score": 0.45, "freshness_score": 0.5},
            )
        )
        for i in range(6):
            svc.ingest_opportunity(
                IngestOpportunityRequest(
                    strategy_id=strategy.strategy_id,
                    source="evergreen",
                    title=f"Backlog item {i}",
                    pillar="character" if i % 2 == 0 else "evergreen",
                    payload={"opportunity_score": 0.4 + i * 0.02, "freshness_score": 0.5},
                )
            )

        plan = svc.create_plan(CreatePlanRequest(strategy_id=strategy.strategy_id, days=7))
        assert plan.items
        assert len(plan.items) <= 10  # capacity
        assert any(it.priority for it in plan.items)
        cal = svc.calendar(strategy.strategy_id)
        assert len(cal) == len([i for i in plan.items if i.status in {"planned", "scheduled"}])

        # Dynamic replan: force urgent into calendar
        # Ensure evergreen exists as replaceable
        assert evergreen.status in {"accepted", "planned"}
        replanned = svc.replan(
            ReplanRequest(plan_id=plan.plan_id, force_trend_id="trend_urgent_1")
        )
        assert replanned.version >= plan.version
        titles = [i.title for i in replanned.items if i.status == "scheduled"]
        assert any(t and "reveal" in t.lower() for t in titles) or any(
            i.opportunity_id == urgent.opportunity_id for i in replanned.items if i.status == "scheduled"
        )

        # Execute → orchestration handoff (brief only)
        jobs = svc.execute(
            ExecuteRequest(
                strategy_id=strategy.strategy_id,
                plan_id=replanned.plan_id,
                max_jobs=1,
                run_pipeline=False,
                orchestration_mode="autonomous",
            )
        )
        assert jobs
        assert jobs[0]["orchestration_job_id"]

        decisions = svc.decisions(strategy.strategy_id)
        assert any(d["decision_type"] in {"plan_created", "dynamic_replan", "opportunity_scored"} for d in decisions)

        health = svc.health(strategy.strategy_id)
        assert health["note"]

    events = {e.event_type for e in get_bus().history}
    assert EventType.STRATEGY_CREATED in events
    assert EventType.OPPORTUNITY_SCORED in events
    assert EventType.PLAN_CREATED in events or EventType.PLAN_REPLANNED in events
    assert EventType.CONTENT_EXECUTION_REQUESTED in events


def test_pause_blocks_ingest(db_url: str) -> None:
    with get_session(db_url) as session:
        svc = StrategyService(session)
        s = svc.create_strategy(CreateStrategyRequest(name="paused_test"))
        svc.pause(s.strategy_id)
        try:
            svc.ingest_opportunity(
                IngestOpportunityRequest(
                    strategy_id=s.strategy_id,
                    source="trend",
                    title="x",
                    payload={"opportunity_score": 0.8},
                )
            )
            assert False, "should raise"
        except ValueError as exc:
            assert "paused" in str(exc)
