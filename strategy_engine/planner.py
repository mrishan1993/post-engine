from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from strategy_engine.portfolio import (
    apply_learning_to_mix,
    capacity_slots,
    detect_content_debt,
    detect_saturation,
)
from strategy_engine.schemas import PlanItemOut, PlanOut, StrategyProfile
from db.models import ContentPlan, ContentPlanItem, StrategyDecisionLog, StrategyOpportunity


PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def build_plan(
    session: Session,
    *,
    strategy_id: str,
    profile: StrategyProfile,
    opportunities: list[StrategyOpportunity],
    period_start: datetime,
    period_end: datetime,
    learning_brief: dict[str, Any] | None = None,
    previous_plan: ContentPlan | None = None,
) -> tuple[ContentPlan, list[ContentPlanItem], list[str], dict[str, float]]:
    now = datetime.now(timezone.utc)
    days = max(1, int((period_end - period_start).total_seconds() // 86400) or 7)
    slots = capacity_slots(profile, days)
    mix = apply_learning_to_mix(profile, learning_brief)

    # Filter usable opportunities
    usable: list[StrategyOpportunity] = []
    for opp in opportunities:
        if opp.status in {"rejected", "cancelled", "expired", "published", "learned"}:
            continue
        exp = _aware(opp.expiration_at)
        if exp and exp < now:
            opp.status = "expired"
            continue
        usable.append(opp)

    usable.sort(
        key=lambda o: (
            PRIORITY_ORDER.get(o.priority or "P3", 3),
            -(float(o.strategic_score or 0)),
            _aware(o.expiration_at) or datetime.max.replace(tzinfo=timezone.utc),
        )
    )

    # Reserve experiment capacity
    reserve = float((profile.experimentation_policy or {}).get("reserve_pct") or 0.1)
    experiment_slots = max(1, int(round(slots * reserve))) if slots >= 5 else (1 if slots >= 3 else 0)
    selected: list[StrategyOpportunity] = []
    experiments = [o for o in usable if (o.source == "experiment" or o.pillar == "experiment")]
    non_exp = [o for o in usable if o not in experiments]

    for o in experiments[:experiment_slots]:
        selected.append(o)
    remaining = slots - len(selected)

    # Fill by mix targets greedily
    pillar_counts: dict[str, int] = {}
    for o in non_exp:
        if len(selected) >= slots:
            break
        pillar = (o.pillar or o.source or "evergreen").lower()
        if pillar == "trends":
            pillar = "trend"
        target = float(mix.get(pillar, 0.15))
        allowed = max(1, int(round(target * slots)))
        if pillar_counts.get(pillar, 0) >= allowed and len(selected) < remaining:
            # still allow if under total capacity and high priority
            if (o.priority or "P3") not in {"P0", "P1"}:
                continue
        selected.append(o)
        pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1
        if len([x for x in selected if x not in experiments[:experiment_slots]]) >= remaining:
            # recount carefully
            pass
        if len(selected) >= slots:
            break

    # If still short, fill with next best
    if len(selected) < slots:
        for o in non_exp:
            if o in selected:
                continue
            selected.append(o)
            if len(selected) >= slots:
                break

    selected = selected[:slots]

    warnings: list[str] = []
    if len(usable) > slots:
        warnings.append(f"Capacity {slots}/period; {len(usable) - slots} opportunities remain in backlog")

    # Schedule across days
    per_day = max(1, int((profile.capacity or {}).get("reels_per_day") or 2))
    items: list[ContentPlanItem] = []
    day_cursor = period_start
    day_count = 0
    for i, opp in enumerate(selected):
        if day_count >= per_day:
            day_cursor = day_cursor + timedelta(days=1)
            day_count = 0
        # Prefer morning/evening slots
        hour = 11 if day_count % 2 == 0 else 19
        scheduled = day_cursor.replace(hour=hour, minute=0, second=0, microsecond=0)
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        item = ContentPlanItem(
            id=str(uuid4()),
            plan_id="pending",
            opportunity_id=opp.id,
            platform=opp.platform,
            pillar=opp.pillar or opp.source,
            content_type=opp.format,
            priority=opp.priority or "P3",
            scheduled_at=scheduled,
            status="scheduled",
            slot_meta={"title": opp.title, "source": opp.source, "score": float(opp.strategic_score or 0)},
        )
        items.append(item)
        day_count += 1
        opp.status = "planned" if opp.status in {"accepted", "detected", "evaluating", "deferred"} else opp.status

    debt = detect_content_debt(
        profile,
        [it.pillar for it in items],
        horizon_slots=slots,
    )
    if debt:
        warnings.append(f"Content debt detected: {debt}")

    sat = detect_saturation(
        [str((it.slot_meta or {}).get("title") or "")[:40] for it in items],
        [it.pillar or "" for it in items],
        [it.content_type or "" for it in items],
        max_same_hook_in_10=int((profile.brand_constraints or {}).get("max_same_hook_in_10") or 3),
    )
    warnings.extend(sat)

    version = 1
    if previous_plan:
        previous_plan.status = "superseded"
        version = int(previous_plan.version or 1) + 1

    plan = ContentPlan(
        id=str(uuid4()),
        strategy_id=strategy_id,
        period_start=period_start,
        period_end=period_end,
        objectives=[o.model_dump() for o in profile.business_objectives],
        content_mix=mix,
        capacity={"slots": slots, "days": days, **(profile.capacity or {})},
        status="active",
        version=version,
        created_at=now,
        updated_at=now,
    )
    session.add(plan)
    session.flush()
    for it in items:
        it.plan_id = plan.id
        session.add(it)
    session.flush()

    get_bus().publish(
        EventType.PLAN_CREATED if version == 1 else EventType.PLAN_REPLANNED,
        {
            "plan_id": plan.id,
            "strategy_id": strategy_id,
            "item_count": len(items),
            "version": version,
            "warnings": warnings,
        },
        producer="strategy-engine",
    )
    return plan, items, warnings, debt


def replan_with_urgent_trend(
    session: Session,
    *,
    plan: ContentPlan,
    profile: StrategyProfile,
    opportunities: list[StrategyOpportunity],
    urgent: StrategyOpportunity,
) -> tuple[ContentPlan, list[str]]:
    """Replace lowest-value non-P0 item if urgent trend is higher value."""
    items = list(
        session.scalars(
            select(ContentPlanItem).where(
                ContentPlanItem.plan_id == plan.id,
                ContentPlanItem.status.in_(["planned", "scheduled"]),
            )
        ).all()
    )
    if not items:
        return plan, ["no items to replace"]

    urgent_score = float(urgent.strategic_score or 0)
    # Find weakest evergreen/character slot
    candidates = []
    for it in items:
        if (it.priority or "P3") == "P0":
            continue
        meta_score = float((it.slot_meta or {}).get("score") or 0)
        if (it.pillar or "").lower() in {"evergreen", "education", "character"} or meta_score < urgent_score:
            candidates.append((meta_score, it))
    if not candidates:
        return plan, ["no replaceable slots (all P0 or higher value)"]

    candidates.sort(key=lambda x: x[0])
    _, victim = candidates[0]
    victim_score = float((victim.slot_meta or {}).get("score") or 0)
    if urgent_score < victim_score + 0.05:
        return plan, ["urgent trend not sufficiently stronger than existing slot"]

    victim.status = "deferred"
    if victim.opportunity_id:
        old = session.get(StrategyOpportunity, victim.opportunity_id)
        if old and old.status == "planned":
            old.status = "deferred"

    # Schedule urgent into victim's slot
    new_item = ContentPlanItem(
        id=str(uuid4()),
        plan_id=plan.id,
        opportunity_id=urgent.id,
        platform=urgent.platform,
        pillar=urgent.pillar or "trend",
        content_type=urgent.format,
        priority=urgent.priority or "P0",
        scheduled_at=victim.scheduled_at,
        status="scheduled",
        slot_meta={
            "title": urgent.title,
            "source": urgent.source,
            "score": urgent_score,
            "replaced_item_id": victim.id,
        },
    )
    session.add(new_item)
    urgent.status = "planned"
    urgent.priority = "P0"
    plan.version = int(plan.version or 1) + 1
    plan.updated_at = datetime.now(timezone.utc)
    session.flush()

    reason = (
        f"Replace item {victim.id[:8]} (score={victim_score:.2f}) with trend "
        f"{urgent.id[:8]} (score={urgent_score:.2f}) due to urgency"
    )
    session.add(
        StrategyDecisionLog(
            id=str(uuid4()),
            strategy_id=plan.strategy_id,
            plan_id=plan.id,
            decision_type="dynamic_replan",
            decision={
                "deferred_item_id": victim.id,
                "inserted_opportunity_id": urgent.id,
                "scheduled_at": victim.scheduled_at.isoformat() if victim.scheduled_at else None,
            },
            reason=reason,
            expected_outcome={"delta_score": round(urgent_score - victim_score, 4)},
            model_version="strategy_planner_v1",
        )
    )
    session.flush()
    get_bus().publish(
        EventType.CONTENT_DEFERRED,
        {"plan_id": plan.id, "item_id": victim.id},
        producer="strategy-engine",
    )
    get_bus().publish(
        EventType.CONTENT_SCHEDULED,
        {"plan_id": plan.id, "opportunity_id": urgent.id, "item_id": new_item.id},
        producer="strategy-engine",
    )
    get_bus().publish(
        EventType.PLAN_REPLANNED,
        {"plan_id": plan.id, "reason": reason},
        producer="strategy-engine",
    )
    return plan, [reason]


def plan_to_out(
    session: Session,
    plan: ContentPlan,
    *,
    warnings: list[str] | None = None,
    debt: dict[str, float] | None = None,
) -> PlanOut:
    items = list(
        session.scalars(
            select(ContentPlanItem)
            .where(ContentPlanItem.plan_id == plan.id)
            .order_by(ContentPlanItem.scheduled_at.asc())
        ).all()
    )
    return PlanOut(
        plan_id=plan.id,
        strategy_id=plan.strategy_id,
        period_start=plan.period_start,
        period_end=plan.period_end,
        objectives=list(plan.objectives or []),
        content_mix=dict(plan.content_mix or {}),
        capacity=dict(plan.capacity or {}),
        status=plan.status,
        version=int(plan.version or 1),
        items=[
            PlanItemOut(
                item_id=it.id,
                opportunity_id=it.opportunity_id,
                platform=it.platform,
                pillar=it.pillar,
                content_type=it.content_type,
                priority=it.priority,
                scheduled_at=it.scheduled_at,
                status=it.status,
                title=(it.slot_meta or {}).get("title"),
            )
            for it in items
        ],
        warnings=warnings or [],
        content_debt=debt or {},
    )
