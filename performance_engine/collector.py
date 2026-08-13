from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from performance_engine.benchmarks import (
    compute_benchmarks,
    default_velocity_share_benchmarks,
)
from performance_engine.derived import compute_derived, performance_vector
from performance_engine.providers import get_analytics_provider
from performance_engine.schedule import next_interval_sec, poll_tier_for_age
from performance_engine.schemas import CanonicalMetrics, ContentFingerprint
from performance_engine.viral import major_dropoff, transition_viral_state
from db.models import (
    AnalyticsCollectionJob,
    AudienceSnapshot,
    PerformanceSnapshot,
    PerformanceTimeseries,
    PlatformMetricResponse,
    PostAnalytics,
    PublicationReceipt,
    RetentionCurve,
)

TS_METRICS = ("views", "likes", "comments", "shares", "saves", "reach")


class PerformanceCollector:
    def __init__(self, session: Session):
        self.session = session

    def start_tracking(
        self,
        publication_id: str,
        *,
        content_fingerprint: ContentFingerprint | dict[str, Any] | None = None,
        prediction: dict[str, Any] | None = None,
        collect_now: bool = True,
        simulate_age_sec: int | None = None,
        growth_profile: str = "normal",
    ) -> AnalyticsCollectionJob:
        receipt = self._get_receipt(publication_id)
        existing = self.session.scalar(
            select(AnalyticsCollectionJob).where(
                AnalyticsCollectionJob.publication_id == receipt.id,
                AnalyticsCollectionJob.status == "active",
            )
        )
        if existing:
            job = existing
        else:
            job = AnalyticsCollectionJob(
                id=str(uuid4()),
                publication_id=receipt.id,
                platform=receipt.platform,
                status="active",
                poll_tier="high",
                next_collect_at=datetime.now(timezone.utc),
                snapshot_count=0,
                lineage={
                    **(receipt.lineage or {}),
                    "content_id": receipt.content_id,
                    "prediction_id": (receipt.lineage or {}).get("prediction_id"),
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(job)
            self.session.flush()
            get_bus().publish(
                EventType.ANALYTICS_TRACKING_STARTED,
                {
                    "job_id": job.id,
                    "publication_id": receipt.id,
                    "platform": receipt.platform,
                    "content_id": receipt.content_id,
                    "prediction_id": (receipt.lineage or {}).get("prediction_id"),
                },
                producer="performance-engine",
            )

        # Ensure analytics row exists with fingerprint / prediction link
        fp = None
        if content_fingerprint:
            fp = (
                content_fingerprint.model_dump()
                if isinstance(content_fingerprint, ContentFingerprint)
                else dict(content_fingerprint)
            )
        analytics = self.session.get(PostAnalytics, receipt.id)
        if not analytics:
            analytics = PostAnalytics(
                publication_id=receipt.id,
                content_id=receipt.content_id,
                prediction_id=(receipt.lineage or {}).get("prediction_id"),
                platform=receipt.platform,
                viral_state="normal",
                content_fingerprint=fp,
                prediction_link=prediction or {},
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(analytics)
        else:
            if fp:
                analytics.content_fingerprint = fp
            if prediction:
                analytics.prediction_link = {
                    **(analytics.prediction_link or {}),
                    **prediction,
                }
        self.session.flush()

        if collect_now:
            self.collect(
                receipt.id,
                simulate_age_sec=simulate_age_sec,
                growth_profile=growth_profile,
            )
        return job

    def collect(
        self,
        publication_id: str,
        *,
        simulate_age_sec: int | None = None,
        growth_profile: str | None = None,
    ) -> PerformanceSnapshot:
        receipt = self._get_receipt(publication_id)
        provider = get_analytics_provider(receipt.platform)
        published_at = receipt.published_at or receipt.created_at
        if published_at and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age = (
            int(simulate_age_sec)
            if simulate_age_sec is not None
            else int((now - published_at).total_seconds())
            if published_at
            else 0
        )
        analytics = self.session.get(PostAnalytics, receipt.id)
        profile = growth_profile or "normal"
        if analytics and (analytics.content_fingerprint or {}).get("growth_profile"):
            profile = str((analytics.content_fingerprint or {}).get("growth_profile"))

        get_bus().publish(
            EventType.ANALYTICS_COLLECTION_STARTED,
            {"publication_id": receipt.id, "age_sec": age, "platform": receipt.platform},
            producer="performance-engine",
        )

        result = provider.get_post_metrics(
            receipt.external_post_id or receipt.id,
            age_since_publish_sec=age,
            growth_profile=profile,
            seed=receipt.id,
        )

        raw = PlatformMetricResponse(
            id=str(uuid4()),
            publication_id=receipt.id,
            platform=receipt.platform,
            endpoint=result.endpoint,
            captured_at=now,
            response=result.raw_response,
            http_status=result.http_status,
        )
        self.session.add(raw)
        self.session.flush()

        prev = self.session.scalars(
            select(PerformanceSnapshot)
            .where(PerformanceSnapshot.publication_id == receipt.id)
            .order_by(PerformanceSnapshot.captured_at.desc())
        ).first()
        prev_metrics = CanonicalMetrics.model_validate(prev.metrics) if prev else None
        prev_derived = (prev.derived or {}) if prev else {}
        delta_hours = None
        if prev and prev.age_since_publish_sec is not None:
            delta_hours = max((age - int(prev.age_since_publish_sec)) / 3600.0, 1e-6)

        derived = compute_derived(
            result.metrics,
            prev_views=prev_metrics.views if prev_metrics else None,
            prev_shares=prev_metrics.shares if prev_metrics else None,
            prev_velocity=float(prev_derived.get("view_velocity_per_hour") or 0) or None,
            delta_hours=delta_hours,
        )

        snap = PerformanceSnapshot(
            id=str(uuid4()),
            publication_id=receipt.id,
            platform=receipt.platform,
            account_id=receipt.social_account_id,
            captured_at=now,
            age_since_publish_sec=age,
            metrics=result.metrics.model_dump(),
            derived=derived.model_dump(),
            raw_response_id=raw.id,
        )
        self.session.add(snap)

        for name in TS_METRICS:
            val = getattr(result.metrics, name, None)
            if val is None:
                continue
            self.session.add(
                PerformanceTimeseries(
                    id=str(uuid4()),
                    publication_id=receipt.id,
                    metric=name,
                    timestamp=now,
                    value=float(val),
                    source=receipt.platform,
                )
            )

        # Retention (replace prior curve for latest capture)
        for old in self.session.scalars(
            select(RetentionCurve).where(RetentionCurve.publication_id == receipt.id)
        ).all():
            self.session.delete(old)
        for pt in result.retention:
            self.session.add(
                RetentionCurve(
                    id=str(uuid4()),
                    publication_id=receipt.id,
                    timestamp_sec=pt.timestamp_sec,
                    retention_percent=pt.retention_percent,
                    source=receipt.platform,
                    captured_at=now,
                )
            )

        if result.audience:
            aud = result.audience
            if result.metrics.non_follower_reach is not None:
                aud.non_follower_reach = result.metrics.non_follower_reach
            self.session.add(
                AudienceSnapshot(
                    id=str(uuid4()),
                    publication_id=receipt.id,
                    captured_at=now,
                    follower_count=aud.follower_count,
                    non_follower_reach=aud.non_follower_reach,
                    demographics=aud.demographics,
                    geography=aud.geography,
                )
            )

        self._upsert_analytics(
            receipt,
            result.metrics,
            derived,
            age,
            now,
            retention=[p.model_dump() for p in result.retention],
        )
        self._update_job(receipt.id, age, derived)
        self.session.flush()

        get_bus().publish(
            EventType.PERFORMANCE_SNAPSHOT_CAPTURED,
            {
                "publication_id": receipt.id,
                "snapshot_id": snap.id,
                "views": result.metrics.views,
                "age_sec": age,
                "virality_score": derived.virality_score,
            },
            producer="performance-engine",
        )
        get_bus().publish(
            EventType.ANALYTICS_COLLECTION_COMPLETED,
            {"publication_id": receipt.id, "snapshot_id": snap.id},
            producer="performance-engine",
        )
        return snap

    def _upsert_analytics(
        self,
        receipt: PublicationReceipt,
        metrics: CanonicalMetrics,
        derived: Any,
        age: int,
        now: datetime,
        *,
        retention: list[dict[str, Any]] | None = None,
    ) -> None:
        row = self.session.get(PostAnalytics, receipt.id)
        if not row:
            row = PostAnalytics(publication_id=receipt.id)
            self.session.add(row)
        row.content_id = receipt.content_id
        row.prediction_id = (receipt.lineage or {}).get("prediction_id")
        row.platform = receipt.platform
        row.current_views = metrics.views
        row.current_likes = metrics.likes
        row.current_comments = metrics.comments
        row.current_shares = metrics.shares
        row.current_saves = metrics.saves
        row.current_reach = metrics.reach
        row.followers_gained = metrics.followers_gained
        row.engagement_rate = derived.engagement_rate
        row.share_rate = derived.share_rate
        row.save_rate = derived.save_rate
        row.completion_rate = metrics.completion_rate
        row.weighted_engagement = derived.weighted_engagement
        row.virality_score = derived.virality_score
        row.view_velocity_per_hour = derived.view_velocity_per_hour
        row.share_velocity_per_hour = derived.share_velocity_per_hour
        row.acceleration = derived.acceleration
        row.engagement_formula_version = derived.engagement_formula_version
        row.virality_model_version = derived.virality_model_version
        row.performance_vector = performance_vector(metrics, derived)

        # First-hour bucket
        fh = dict(row.first_hour or {})
        if age <= 5 * 60:
            fh["views_5m"] = metrics.views
        if age <= 15 * 60:
            fh["views_15m"] = metrics.views
        if age <= 30 * 60:
            fh["views_30m"] = metrics.views
        if age <= 3600:
            fh["views_1h"] = metrics.views
            fh["likes_1h"] = metrics.likes
            fh["shares_1h"] = metrics.shares
            fh["comments_1h"] = metrics.comments
        row.first_hour = fh

        # Benchmarks + viral state
        character = (row.content_fingerprint or {}).get("character")
        benches = compute_benchmarks(
            self.session,
            publication_id=receipt.id,
            metric="views",
            character=character,
            platform=receipt.platform,
        )
        char_or_global = next((b for b in benches if b.dimension == "character"), None) or benches[-1]
        row.performance_index = char_or_global.performance_index
        row.percentile_rank = char_or_global.percentile_rank

        defaults = default_velocity_share_benchmarks(character)
        vel_bench = compute_benchmarks(
            self.session,
            publication_id=receipt.id,
            metric="view_velocity",
            character=character,
            platform=receipt.platform,
        )
        share_bench = compute_benchmarks(
            self.session,
            publication_id=receipt.id,
            metric="share_rate",
            character=character,
            platform=receipt.platform,
        )
        p95_vel = next((b.p95 for b in vel_bench if b.sample_size > 0), defaults["p95_velocity"])
        p75_share = next(
            (b.p75 for b in share_bench if b.sample_size > 0), defaults["p75_share_rate"]
        )
        # Prefer defaults when cold-start synthetic values are tiny
        if p95_vel < 1000:
            p95_vel = defaults["p95_velocity"]
        if p75_share < 0.001:
            p75_share = defaults["p75_share_rate"]

        prev_state = row.viral_state or "normal"
        new_state = transition_viral_state(
            prev_state,
            derived=derived,
            benchmark_p95_velocity=float(p95_vel),
            benchmark_p75_share_rate=float(p75_share),
        )
        if new_state != prev_state:
            get_bus().publish(
                EventType.VIRAL_STATE_CHANGED,
                {
                    "publication_id": receipt.id,
                    "from": prev_state,
                    "to": new_state,
                    "views": metrics.views,
                    "view_velocity_per_hour": derived.view_velocity_per_hour,
                },
                producer="performance-engine",
            )
            if new_state in {"accelerating", "viral", "second_wave"}:
                get_bus().publish(
                    EventType.VIRAL_DETECTED,
                    {
                        "publication_id": receipt.id,
                        "state": new_state,
                        "views": metrics.views,
                        "share_rate": derived.share_rate,
                        "view_velocity_per_hour": derived.view_velocity_per_hour,
                    },
                    producer="performance-engine",
                )
        row.viral_state = new_state

        # Prediction link actuals
        pred = dict(row.prediction_link or {})
        if pred:
            pred["actual"] = {
                "virality": derived.virality_score,
                "engagement": derived.engagement_rate,
                "completion": metrics.completion_rate,
                "views": metrics.views,
            }
            row.prediction_link = pred

        row.updated_at = now

        drop = major_dropoff(retention or [])
        if drop and drop.get("severity") == "high":
            get_bus().publish(
                EventType.LOW_RETENTION_DETECTED,
                {"publication_id": receipt.id, "dropoff": drop},
                producer="performance-engine",
            )

    def _update_job(self, publication_id: str, age: int, derived: Any) -> None:
        job = self.session.scalar(
            select(AnalyticsCollectionJob).where(
                AnalyticsCollectionJob.publication_id == publication_id,
                AnalyticsCollectionJob.status == "active",
            )
        )
        if not job:
            return
        accelerated = derived.view_velocity_per_hour > 100_000
        tier = poll_tier_for_age(age)
        if accelerated:
            tier = "high"
        job.poll_tier = tier
        job.snapshot_count = int(job.snapshot_count or 0) + 1
        job.last_collected_at = datetime.now(timezone.utc)
        job.next_collect_at = datetime.now(timezone.utc) + timedelta(
            seconds=next_interval_sec(tier, accelerated=accelerated)
        )
        job.updated_at = datetime.now(timezone.utc)
        job.error = None

    def _get_receipt(self, publication_id: str) -> PublicationReceipt:
        row = self.session.get(PublicationReceipt, publication_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(PublicationReceipt).where(
                    PublicationReceipt.id.startswith(publication_id)
                )
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("publication receipt not found")
        return rows[0]
