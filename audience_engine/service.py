from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from audience_engine.clustering import (
    aggregate_demands,
    character_affinity_from_interactions,
    cluster_topics,
)
from audience_engine.health import health_from_batch
from audience_engine.nlp import analyze_comment
from audience_engine.schemas import (
    AcceptOpportunityRequest,
    AlertOut,
    AnalyticsIn,
    CharacterAffinityOut,
    CommentIn,
    CreateSegmentRequest,
    DemandOut,
    IngestBatchRequest,
    InteractionOut,
    OpportunityOut,
    OverviewOut,
    ResolveAlertRequest,
    SegmentOut,
    TopicOut,
)
from db.models import (
    AudienceDemand,
    AudienceIntelligenceSnapshot,
    AudienceIntent,
    AudienceOpportunity,
    AudienceSegment,
    AudienceSignal,
    CharacterAffinity,
    CommunityAlert,
    CommunityInteraction,
    CommunityTopic,
)


DEFAULT_SEGMENTS = [
    ("new_viewers", "exposed", "Recently exposed / first-touch viewers"),
    ("casual_viewers", "viewer", "Occasional watchers"),
    ("followers", "follower", "Account followers"),
    ("returning_viewers", "returning", "Repeat viewers"),
    ("core_fans", "fan", "High-engagement character fans"),
    ("advocates", "advocate", "Sharers and community amplifiers"),
    ("churn_risk", "churn_risk", "Previously engaged, declining activity"),
]


class AudienceService:
    """Audience Intelligence & Community — listen, structure, act."""

    def __init__(self, session: Session):
        self.session = session

    def ensure_default_segments(self) -> list[SegmentOut]:
        existing = {
            s.name: s
            for s in self.session.scalars(select(AudienceSegment)).all()
        }
        out = []
        for name, stage, desc in DEFAULT_SEGMENTS:
            if name in existing:
                out.append(self._segment_out(existing[name]))
                continue
            row = AudienceSegment(
                id=str(uuid4()),
                name=name,
                description=desc,
                criteria={"lifecycle_stage": stage},
                size=0,
                confidence=0.7,
                status="active",
                segment_kind="explicit",
                lifecycle_stage=stage,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(row)
            self.session.flush()
            get_bus().publish(
                EventType.AUDIENCE_SEGMENT_UPDATED,
                {"segment_id": row.id, "name": row.name},
                producer="audience-engine",
            )
            out.append(self._segment_out(row))
        return out

    def create_segment(self, request: CreateSegmentRequest | dict[str, Any]) -> SegmentOut:
        req = (
            request
            if isinstance(request, CreateSegmentRequest)
            else CreateSegmentRequest.model_validate(request)
        )
        row = AudienceSegment(
            id=str(uuid4()),
            name=req.name,
            description=req.description,
            criteria=req.criteria,
            size=req.size,
            confidence=req.confidence,
            status="active",
            segment_kind=req.segment_kind,
            lifecycle_stage=req.lifecycle_stage,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.AUDIENCE_SEGMENT_UPDATED,
            {"segment_id": row.id, "name": row.name, "kind": row.segment_kind},
            producer="audience-engine",
        )
        return self._segment_out(row)

    def ingest(self, request: IngestBatchRequest | dict[str, Any]) -> OverviewOut:
        req = (
            request
            if isinstance(request, IngestBatchRequest)
            else IngestBatchRequest.model_validate(request)
        )
        self.ensure_default_segments()
        segments = {
            s.name: s
            for s in self.session.scalars(select(AudienceSegment)).all()
        }
        seen: set[str] = set()
        classified: list[dict[str, Any]] = []
        noise_count = 0

        for c in req.comments:
            analysis = analyze_comment(
                c.text,
                characters=req.characters,
                likes=c.likes,
                seen_normalized=seen,
            )
            seen.add(analysis["text_normalized"])
            if analysis["is_noise"]:
                noise_count += 1

            segment = self._map_segment(c, segments)
            intent_row = None
            if not analysis["is_noise"]:
                intent_row = AudienceIntent(
                    id=str(uuid4()),
                    segment_id=segment.id if segment else None,
                    intent_type=analysis["intent_type"],
                    subject=(c.text[:200]),
                    volume=1,
                    velocity=0.1,
                    confidence=analysis["intent_confidence"],
                    evidence={"text": c.text[:200], "language": analysis["language"]},
                    content_id=c.content_id or req.content_id,
                    created_at=datetime.now(timezone.utc),
                )
                self.session.add(intent_row)
                self.session.flush()
                get_bus().publish(
                    EventType.AUDIENCE_INTENT_DETECTED,
                    {
                        "intent_id": intent_row.id,
                        "intent_type": intent_row.intent_type,
                        "confidence": float(intent_row.confidence or 0),
                    },
                    producer="audience-engine",
                )

            ix = CommunityInteraction(
                id=str(uuid4()),
                platform=c.platform or req.platform,
                content_id=c.content_id or req.content_id,
                interaction_type="comment",
                text_reference=c.text,
                text_normalized=analysis["text_normalized"],
                segment_id=segment.id if segment else None,
                intent_id=intent_row.id if intent_row else None,
                intent_type=analysis["intent_type"],
                sentiment=analysis["sentiment"],
                emotion=analysis["emotion"],
                language=analysis["language"],
                priority=analysis["priority"],
                is_noise=analysis["is_noise"],
                moderation_flags=analysis["moderation_flags"],
                entities=analysis["entities"],
                timestamp=datetime.now(timezone.utc),
            )
            self.session.add(ix)

            sig = AudienceSignal(
                id=str(uuid4()),
                source="comment",
                content_id=c.content_id or req.content_id,
                segment_id=segment.id if segment else None,
                signal_type="comment",
                value={
                    "text": c.text[:300],
                    "intent": analysis["intent_type"],
                    "sentiment": analysis["sentiment"],
                    "entities": analysis["entities"],
                },
                confidence=analysis["intent_confidence"],
                platform=c.platform or req.platform,
                language=analysis["language"],
                is_noise=analysis["is_noise"],
                timestamp=datetime.now(timezone.utc),
            )
            self.session.add(sig)
            get_bus().publish(
                EventType.AUDIENCE_SIGNAL_DETECTED,
                {"signal_id": sig.id, "signal_type": "comment", "is_noise": sig.is_noise},
                producer="audience-engine",
            )

            classified.append(
                {
                    "id": ix.id,
                    "text": c.text,
                    "text_reference": c.text,
                    "content_id": ix.content_id,
                    "is_noise": analysis["is_noise"],
                    "intent_type": analysis["intent_type"],
                    "sentiment": analysis["sentiment"],
                    "emotion": analysis["emotion"],
                    "language": analysis["language"],
                    "entities": analysis["entities"],
                    "moderation_flags": analysis["moderation_flags"],
                    "priority": analysis["priority"],
                    "segment": segment.name if segment else None,
                }
            )

        for a in req.analytics:
            self._ingest_analytics(a, segments)

        self.session.flush()

        if req.process:
            return self.process_intelligence(
                interactions=classified,
                analytics=[a.model_dump() for a in req.analytics],
                characters=req.characters,
                noise_count=noise_count,
            )
        return self.overview()

    def process_intelligence(
        self,
        *,
        interactions: list[dict[str, Any]] | None = None,
        analytics: list[dict[str, Any]] | None = None,
        characters: list[str] | None = None,
        noise_count: int = 0,
    ) -> OverviewOut:
        if interactions is None:
            rows = list(
                self.session.scalars(
                    select(CommunityInteraction).order_by(CommunityInteraction.timestamp.desc()).limit(500)
                ).all()
            )
            interactions = [
                {
                    "id": r.id,
                    "text": r.text_reference,
                    "text_reference": r.text_reference,
                    "content_id": r.content_id,
                    "is_noise": r.is_noise,
                    "intent_type": r.intent_type,
                    "sentiment": r.sentiment,
                    "emotion": r.emotion,
                    "language": r.language,
                    "entities": r.entities or {},
                    "moderation_flags": r.moderation_flags or [],
                    "priority": float(r.priority or 0),
                }
                for r in rows
            ]
        characters = characters or ["character_a", "character_b"]
        analytics = analytics or []

        # Topics
        topics = cluster_topics(interactions)
        topic_outs: list[TopicOut] = []
        for t in topics:
            # velocity spike alert vs prior topic volume
            prior = self.session.scalar(
                select(CommunityTopic).where(CommunityTopic.topic == t["topic"])
            )
            velocity = float(t["velocity"] or 0)
            if prior and prior.volume and t["volume"] > max(10, int(prior.volume) * 3):
                velocity = float(t["volume"]) / max(1, prior.volume)
                self._alert(
                    "community_topic_velocity",
                    "P1",
                    f"Topic '{t['topic']}' velocity spike",
                    {
                        "yesterday_proxy": prior.volume,
                        "today": t["volume"],
                        "velocity": velocity,
                    },
                    "evaluate_as_trend",
                )
                get_bus().publish(
                    EventType.COMMUNITY_TREND_DETECTED,
                    {"topic": t["topic"], "volume": t["volume"], "velocity": velocity},
                    producer="audience-engine",
                )
            row = prior or CommunityTopic(
                id=str(uuid4()),
                topic=t["topic"],
                created_at=datetime.now(timezone.utc),
            )
            row.volume = t["volume"]
            row.velocity = velocity
            row.sentiment = t["sentiment"]
            row.related_content = t.get("related_content")
            row.keywords = t.get("keywords")
            row.status = "active"
            row.updated_at = datetime.now(timezone.utc)
            if not prior:
                self.session.add(row)
            self.session.flush()
            get_bus().publish(
                EventType.COMMUNITY_TOPIC_DETECTED,
                {"topic_id": row.id, "topic": row.topic, "volume": row.volume},
                producer="audience-engine",
            )
            topic_outs.append(self._topic_out(row))

        # Demands + opportunities
        demands = aggregate_demands(interactions, min_volume=5)
        demand_outs: list[DemandOut] = []
        opp_outs: list[OpportunityOut] = []
        for d in demands:
            demand = AudienceDemand(
                id=str(uuid4()),
                subject=d["subject"],
                type=d["type"],
                volume=d["volume"],
                velocity=d["velocity"],
                strategic_fit=d["strategic_fit"],
                confidence=d["confidence"],
                recommended_action=d["recommended_action"],
                status="confirmed" if (d["confidence"] or 0) >= 0.8 else "detected",
                audience_segments=d["audience_segments"],
                sentiment=d["sentiment"],
                evidence=d["evidence"],
                related_content=d.get("related_content"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(demand)
            self.session.flush()
            get_bus().publish(
                EventType.AUDIENCE_DEMAND_DETECTED,
                {
                    "demand_id": demand.id,
                    "subject": demand.subject,
                    "volume": demand.volume,
                    "confidence": float(demand.confidence or 0),
                },
                producer="audience-engine",
            )
            demand_outs.append(self._demand_out(demand))

            if (d["confidence"] or 0) >= 0.65 and (d["strategic_fit"] or 0) >= 0.65:
                opp = self._create_opportunity_from_demand(demand)
                opp_outs.append(self._opportunity_out(opp))

        # Character affinity
        affinities = character_affinity_from_interactions(interactions, characters)
        aff_outs: list[CharacterAffinityOut] = []
        for a in affinities:
            existing = self.session.scalar(
                select(CharacterAffinity).where(CharacterAffinity.character_slug == a["character_slug"])
            )
            prev = float(existing.affinity_score or 0) if existing else None
            row = existing or CharacterAffinity(
                id=str(uuid4()),
                character_slug=a["character_slug"],
            )
            row.affinity_score = a["affinity_score"]
            row.sentiment = a["sentiment"]
            row.trend = a["trend"]
            row.relationships = a.get("relationships")
            row.audience_requests = a.get("audience_requests")
            row.updated_at = datetime.now(timezone.utc)
            if not existing:
                self.session.add(row)
            self.session.flush()
            get_bus().publish(
                EventType.CHARACTER_AFFINITY_CHANGED,
                {
                    "character_slug": row.character_slug,
                    "affinity_score": float(row.affinity_score or 0),
                    "previous": prev,
                    "trend": row.trend,
                },
                producer="audience-engine",
            )
            if a.get("relationships"):
                get_bus().publish(
                    EventType.CHARACTER_RELATIONSHIP_SIGNAL_DETECTED,
                    {
                        "character_slug": row.character_slug,
                        "relationships": a["relationships"],
                    },
                    producer="audience-engine",
                )
            aff_outs.append(self._affinity_out(row))

        # Health + alerts
        score, components, alert_specs = health_from_batch(interactions, analytics=analytics)
        alert_outs: list[AlertOut] = []
        for spec in alert_specs:
            alert_outs.append(
                self._alert(
                    spec["alert_type"],
                    spec["severity"],
                    spec["subject"],
                    spec["evidence"],
                    spec["recommended_action"],
                )
            )
        get_bus().publish(
            EventType.COMMUNITY_HEALTH_CHANGED,
            {"community_health": score, "components": components},
            producer="audience-engine",
        )
        get_bus().publish(
            EventType.COMMUNITY_SENTIMENT_CHANGED,
            {"sentiment": components},
            producer="audience-engine",
        )

        # Churn proxy from analytics
        for a in analytics:
            unfollows = float(a.get("unfollows") or 0)
            follows = float(a.get("follows") or 0)
            ret = float(a.get("returning_viewer_rate") or 1)
            if unfollows > follows * 0.5 or ret < 0.2:
                alert_outs.append(
                    self._alert(
                        "audience_churn_risk",
                        "P1",
                        "Previously engaged segment showing churn risk",
                        {"analytics": a},
                        "increase_relationship_oriented_content",
                    )
                )
                get_bus().publish(
                    EventType.AUDIENCE_CHURN_RISK_DETECTED,
                    {"content_id": a.get("content_id"), "returning_viewer_rate": ret},
                    producer="audience-engine",
                )

        intelligence = {
            "segments": list(
                {
                    "name": s.name,
                    "lifecycle_stage": s.lifecycle_stage,
                    "size": s.size,
                }
                for s in self.session.scalars(select(AudienceSegment)).all()
            ),
            "interests": [t.topic for t in topic_outs[:10]],
            "behaviors": components,
            "preferences": {"formats": ["reel"], "characters": characters},
            "intent": [d.type for d in demand_outs],
            "sentiment": components,
            "character_affinity": [a.model_dump() for a in aff_outs],
            "community_health": score,
            "evolution": {"note": "versioned snapshot"},
        }
        snap = AudienceIntelligenceSnapshot(
            id=str(uuid4()),
            version=1,
            payload=intelligence,
            community_health=score,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(snap)
        self._soft_learning_handoff(intelligence, score)
        self.session.flush()

        return OverviewOut(
            community_health=score,
            signal_count=len(interactions),
            interaction_count=len(interactions),
            noise_filtered=noise_count or sum(1 for i in interactions if i.get("is_noise")),
            topics=topic_outs,
            demands=demand_outs,
            opportunities=opp_outs,
            alerts=alert_outs,
            segments=[self._segment_out(s) for s in self.session.scalars(select(AudienceSegment)).all()],
            character_affinity=aff_outs,
            intelligence=intelligence,
        )

    def overview(self) -> OverviewOut:
        topics = [
            self._topic_out(t)
            for t in self.session.scalars(
                select(CommunityTopic).order_by(CommunityTopic.volume.desc()).limit(20)
            ).all()
        ]
        demands = [
            self._demand_out(d)
            for d in self.session.scalars(
                select(AudienceDemand).order_by(AudienceDemand.volume.desc()).limit(20)
            ).all()
        ]
        opps = [
            self._opportunity_out(o)
            for o in self.session.scalars(
                select(AudienceOpportunity).order_by(AudienceOpportunity.created_at.desc()).limit(20)
            ).all()
        ]
        alerts = [
            self._alert_out(a)
            for a in self.session.scalars(
                select(CommunityAlert)
                .where(CommunityAlert.status == "open")
                .order_by(CommunityAlert.created_at.desc())
                .limit(20)
            ).all()
        ]
        snap = self.session.scalar(
            select(AudienceIntelligenceSnapshot).order_by(AudienceIntelligenceSnapshot.created_at.desc())
        )
        signal_count = int(self.session.scalar(select(func.count()).select_from(AudienceSignal)) or 0)
        interaction_count = int(
            self.session.scalar(select(func.count()).select_from(CommunityInteraction)) or 0
        )
        noise_filtered = int(
            self.session.scalar(
                select(func.count())
                .select_from(CommunityInteraction)
                .where(CommunityInteraction.is_noise.is_(True))
            )
            or 0
        )
        return OverviewOut(
            community_health=float(snap.community_health or 0) if snap else 0.0,
            signal_count=signal_count,
            interaction_count=interaction_count,
            noise_filtered=noise_filtered,
            topics=topics,
            demands=demands,
            opportunities=opps,
            alerts=alerts,
            segments=[self._segment_out(s) for s in self.session.scalars(select(AudienceSegment)).all()],
            character_affinity=[
                self._affinity_out(a)
                for a in self.session.scalars(select(CharacterAffinity)).all()
            ],
            intelligence=(snap.payload if snap else {}),
        )

    def accept_opportunity(
        self, request: AcceptOpportunityRequest | dict[str, Any]
    ) -> OpportunityOut:
        req = (
            request
            if isinstance(request, AcceptOpportunityRequest)
            else AcceptOpportunityRequest.model_validate(request)
        )
        opp = self.session.get(AudienceOpportunity, req.opportunity_id)
        if not opp:
            raise ValueError(f"opportunity not found: {req.opportunity_id}")
        opp.status = "acted_upon"

        if req.push_to_strategy and req.strategy_id:
            try:
                from strategy_engine.schemas import IngestOpportunityRequest
                from strategy_engine.service import StrategyService

                so = StrategyService(self.session).ingest_opportunity(
                    IngestOpportunityRequest(
                        strategy_id=req.strategy_id,
                        source="audience_request",
                        title=opp.subject,
                        pillar="character",
                        platform="instagram",
                        payload={
                            "opportunity_score": float(opp.confidence or 0.8),
                            "velocity_score": float(opp.velocity or 0.5),
                            "freshness_score": 0.85,
                            "saturation_score": 0.2,
                            "audience_opportunity_id": opp.id,
                            "demand_id": opp.demand_id,
                            "volume": opp.volume,
                            "strategic_fit": float(opp.strategic_fit or 0.8),
                            "evidence": opp.evidence,
                        },
                    )
                )
                opp.strategy_opportunity_id = so.opportunity_id
            except Exception:  # noqa: BLE001
                pass

        if req.push_to_campaign and req.campaign_id:
            try:
                from campaign_engine.schemas import CreateEpisodeRequest
                from campaign_engine.service import CampaignService
                from db.models import ContentSeries

                series_id = req.series_id
                if not series_id:
                    series = self.session.scalar(
                        select(ContentSeries).where(ContentSeries.campaign_id == req.campaign_id)
                    )
                    series_id = series.id if series else None
                if series_id:
                    ep = CampaignService(self.session).create_episode(
                        CreateEpisodeRequest(
                            series_id=series_id,
                            title=opp.subject,
                            objective="audience_demand",
                            premise=opp.subject,
                            hook=f"You asked for this: {opp.subject}",
                            narrative_role="audience_interaction",
                            audience_role="community",
                            continuity_requirements={
                                "audience_opportunity_id": opp.id,
                                "source": "audience_engine",
                            },
                        )
                    )
                    opp.campaign_episode_id = ep.episode_id
            except Exception:  # noqa: BLE001
                pass

        get_bus().publish(
            EventType.CONTENT_OPPORTUNITY_CREATED,
            {
                "opportunity_id": opp.id,
                "status": opp.status,
                "strategy_opportunity_id": opp.strategy_opportunity_id,
                "campaign_episode_id": opp.campaign_episode_id,
            },
            producer="audience-engine",
        )
        self.session.flush()
        return self._opportunity_out(opp)

    def resolve_alert(self, request: ResolveAlertRequest | dict[str, Any]) -> AlertOut:
        req = (
            request
            if isinstance(request, ResolveAlertRequest)
            else ResolveAlertRequest.model_validate(request)
        )
        alert = self.session.get(CommunityAlert, req.alert_id)
        if not alert:
            raise ValueError(f"alert not found: {req.alert_id}")
        alert.status = req.resolution
        if req.notes:
            evidence = dict(alert.evidence or {})
            evidence["resolution_notes"] = req.notes
            alert.evidence = evidence
        self.session.flush()
        return self._alert_out(alert)

    # ── internals ────────────────────────────────────────────────────────────

    def _map_segment(
        self, comment: CommentIn, segments: dict[str, AudienceSegment]
    ) -> AudienceSegment | None:
        tier = (comment.user_tier or "").lower()
        mapping = {
            "new": "new_viewers",
            "viewer": "casual_viewers",
            "follower": "followers",
            "returning": "returning_viewers",
            "fan": "core_fans",
            "advocate": "advocates",
        }
        name = mapping.get(tier, "followers" if comment.likes > 5 else "casual_viewers")
        return segments.get(name)

    def _ingest_analytics(
        self, a: AnalyticsIn, segments: dict[str, AudienceSegment]
    ) -> None:
        for metric in ("views", "likes", "shares", "comments", "completion_rate", "follows"):
            val = getattr(a, metric, None)
            if val is None:
                continue
            self.session.add(
                AudienceSignal(
                    id=str(uuid4()),
                    source="analytics",
                    content_id=a.content_id,
                    segment_id=None,
                    signal_type=metric,
                    value={"value": val, "platform": a.platform},
                    confidence=0.9,
                    platform=a.platform,
                    language=None,
                    is_noise=False,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        get_bus().publish(
            EventType.AUDIENCE_SIGNAL_DETECTED,
            {"content_id": a.content_id, "signal_type": "analytics_batch"},
            producer="audience-engine",
        )
        # Grow follower segment size proxy
        if a.follows and "followers" in segments:
            segments["followers"].size = int(segments["followers"].size or 0) + int(a.follows)
            segments["followers"].updated_at = datetime.now(timezone.utc)

    def _create_opportunity_from_demand(self, demand: AudienceDemand) -> AudienceOpportunity:
        demand_score = (
            (demand.volume or 0)
            * float(demand.velocity or 0.5)
            * float(demand.strategic_fit or 0.7)
            * float(demand.confidence or 0.7)
        )
        priority = "P1" if demand_score >= 50 else "P2" if demand_score >= 15 else "P3"
        opp = AudienceOpportunity(
            id=str(uuid4()),
            type="content_request",
            subject=demand.subject,
            volume=demand.volume,
            velocity=demand.velocity,
            confidence=demand.confidence,
            strategic_fit=demand.strategic_fit,
            audience_segments=demand.audience_segments,
            sentiment=demand.sentiment,
            recommended_action=demand.recommended_action or "create_episode",
            priority=priority,
            status="actionable",
            demand_id=demand.id,
            evidence={
                **(demand.evidence or {}),
                "demand_score": demand_score,
                "confidence": float(demand.confidence or 0),
                "evidence_count": demand.volume,
            },
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(opp)
        self.session.flush()
        get_bus().publish(
            EventType.CONTENT_REQUEST_DETECTED,
            {"opportunity_id": opp.id, "subject": opp.subject, "priority": opp.priority},
            producer="audience-engine",
        )
        get_bus().publish(
            EventType.CONTENT_OPPORTUNITY_CREATED,
            {
                "opportunity_id": opp.id,
                "subject": opp.subject,
                "confidence": float(opp.confidence or 0),
                "priority": opp.priority,
            },
            producer="audience-engine",
        )
        return opp

    def _alert(
        self,
        alert_type: str,
        severity: str,
        subject: str,
        evidence: dict[str, Any],
        recommended_action: str,
    ) -> AlertOut:
        row = CommunityAlert(
            id=str(uuid4()),
            alert_type=alert_type,
            severity=severity,
            subject=subject,
            evidence=evidence,
            recommended_action=recommended_action,
            status="open",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.COMMUNITY_ALERT_CREATED,
            {
                "alert_id": row.id,
                "alert_type": alert_type,
                "severity": severity,
                "subject": subject,
            },
            producer="audience-engine",
        )
        return self._alert_out(row)

    def _soft_learning_handoff(self, intelligence: dict[str, Any], health: float) -> None:
        try:
            from learning_engine.schemas import CreateObservationRequest
            from learning_engine.service import LearningService

            LearningService(self.session).add_observation(
                CreateObservationRequest(
                    feature_vector={
                        "source": "audience_engine",
                        "interests": intelligence.get("interests"),
                        "intent": intelligence.get("intent"),
                    },
                    outcome_vector={
                        "community_health": health,
                        "sentiment": intelligence.get("sentiment"),
                    },
                    confidence=0.7,
                )
            )
        except Exception:  # noqa: BLE001
            pass

    def _segment_out(self, s: AudienceSegment) -> SegmentOut:
        return SegmentOut(
            segment_id=s.id,
            name=s.name,
            description=s.description,
            size=s.size,
            confidence=float(s.confidence) if s.confidence is not None else None,
            status=s.status,
            segment_kind=s.segment_kind,
            lifecycle_stage=s.lifecycle_stage,
        )

    def _topic_out(self, t: CommunityTopic) -> TopicOut:
        return TopicOut(
            topic_id=t.id,
            topic=t.topic,
            volume=t.volume,
            velocity=float(t.velocity) if t.velocity is not None else None,
            sentiment=t.sentiment or {},
            status=t.status,
            keywords=list(t.keywords or []),
        )

    def _demand_out(self, d: AudienceDemand) -> DemandOut:
        return DemandOut(
            demand_id=d.id,
            subject=d.subject,
            type=d.type,
            volume=d.volume,
            velocity=float(d.velocity) if d.velocity is not None else None,
            confidence=float(d.confidence) if d.confidence is not None else None,
            strategic_fit=float(d.strategic_fit) if d.strategic_fit is not None else None,
            recommended_action=d.recommended_action,
            status=d.status,
            audience_segments=list(d.audience_segments or []),
            sentiment=d.sentiment,
            evidence=d.evidence if isinstance(d.evidence, dict) else {"items": d.evidence or []},
        )

    def _opportunity_out(self, o: AudienceOpportunity) -> OpportunityOut:
        return OpportunityOut(
            opportunity_id=o.id,
            type=o.type,
            subject=o.subject,
            volume=o.volume,
            velocity=float(o.velocity) if o.velocity is not None else None,
            confidence=float(o.confidence) if o.confidence is not None else None,
            strategic_fit=float(o.strategic_fit) if o.strategic_fit is not None else None,
            audience_segments=list(o.audience_segments or []),
            sentiment=o.sentiment,
            recommended_action=o.recommended_action,
            priority=o.priority,
            status=o.status,
            demand_id=o.demand_id,
            evidence=o.evidence or {},
            strategy_opportunity_id=o.strategy_opportunity_id,
            campaign_episode_id=o.campaign_episode_id,
        )

    def _alert_out(self, a: CommunityAlert) -> AlertOut:
        return AlertOut(
            alert_id=a.id,
            alert_type=a.alert_type,
            severity=a.severity,
            subject=a.subject,
            evidence=a.evidence or {},
            recommended_action=a.recommended_action,
            status=a.status,
            created_at=a.created_at,
        )

    def _affinity_out(self, a: CharacterAffinity) -> CharacterAffinityOut:
        return CharacterAffinityOut(
            character_slug=a.character_slug,
            affinity_score=float(a.affinity_score) if a.affinity_score is not None else None,
            sentiment=a.sentiment or {},
            trend=a.trend,
            relationships=a.relationships or {},
        )
