from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from learning_engine.policy import duration_bucket
from db.models import (
    LearningObservation,
    PostAnalytics,
    PublicationReceipt,
    VerificationRun,
)


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def quality_check(
    feature: dict[str, Any],
    outcome: dict[str, Any],
    *,
    verification_status: str | None,
) -> tuple[bool, str | None, dict[str, Any]]:
    flags: dict[str, Any] = {}
    if verification_status and verification_status in {"insufficient_data", "invalid", "pending"}:
        return True, f"verification_status_{verification_status}", {"bad_status": verification_status}
    views = _num(outcome.get("views"))
    if views is None and outcome.get("completion_rate") is None and outcome.get("share_rate") is None:
        return True, "missing_outcomes", {"missing": True}
    if views is not None and views < 0:
        return True, "invalid_metrics", {"views": views}
    # Flag extreme outliers — do not silently drop
    if views is not None and views >= 50_000_000:
        flags["outlier_viral"] = True
        flags["note"] = "extreme outlier flagged for deep dive; retained"
    if verification_status == "early_result":
        flags["early_result"] = True
        flags["note"] = "early window — use cautiously for model training"
    return False, None, flags


def build_vectors_from_verification(run: VerificationRun, session: Session) -> tuple[dict[str, Any], dict[str, Any]]:
    pred = run.prediction_snapshot or {}
    actual = run.actual_snapshot or {}
    metrics = actual.get("metrics") or {}
    segments = pred.get("segments") or {}
    signals = pred.get("signals") or {}
    features_in = pred.get("features") or {}
    predictions = pred.get("predictions") or {}

    analytics = session.get(PostAnalytics, run.publication_id) if run.publication_id else None
    receipt = session.get(PublicationReceipt, run.publication_id) if run.publication_id else None
    fingerprint = (analytics.content_fingerprint if analytics else None) or {}
    lineage = (receipt.lineage if receipt else None) or {}

    published_at = receipt.published_at if receipt else None
    hour = published_at.hour if published_at else None
    dow = published_at.weekday() if published_at else None

    duration = fingerprint.get("duration_sec") or features_in.get("duration_sec")
    character = (
        segments.get("character")
        or fingerprint.get("character")
        or lineage.get("character_slug")
        or ""
    )
    hook_type = segments.get("hook_type") or fingerprint.get("hook_type") or ""
    story_type = segments.get("story_type") or fingerprint.get("story_type") or ""
    trend_category = segments.get("trend_category") or fingerprint.get("trend_category") or ""
    platform = segments.get("platform") or (receipt.platform if receipt else None) or ""

    def _p(key: str) -> float | None:
        node = predictions.get(key)
        if isinstance(node, dict):
            for k in ("probability", "expected", "value"):
                if node.get(k) is not None:
                    return _num(node[k])
        return _num(node)

    feature = {
        "character": str(character) if character else None,
        "platform": str(platform) if platform else None,
        "hook_type": str(hook_type) if hook_type else None,
        "story_type": str(story_type) if story_type else None,
        "trend_category": str(trend_category) if trend_category else None,
        "duration_sec": _num(duration),
        "duration_bucket": duration_bucket(_num(duration)),
        "hour": hour,
        "day_of_week": dow,
        "qa_score": _num(actual.get("qa_score")),
        "model_id": pred.get("model_id") or run.model_id,
        "model_version": pred.get("model_version") or run.model_version,
        "predicted_virality": _p("virality"),
        "predicted_engagement": _p("engagement"),
        "predicted_completion": _p("completion"),
        "predicted_views": _p("views"),
        "signals": signals,
        "diagnosis_primary": (run.diagnosis or {}).get("primary"),
        "confidence_label": (run.result_summary or {}).get("confidence_label"),
        "verification_stage": run.stage,
    }

    outcome = {
        "views": _num(metrics.get("views")),
        "engagement_rate": _num(metrics.get("engagement_rate")),
        "completion_rate": _num(metrics.get("completion_rate")),
        "share_rate": _num(metrics.get("share_rate")),
        "save_rate": _num(metrics.get("save_rate")),
        "virality_score": _num(metrics.get("virality_score")),
        "followers_gained": _num(metrics.get("followers_gained")),
        "viral_state": metrics.get("viral_state") or (analytics.viral_state if analytics else None),
    }
    return feature, outcome


def ingest_verification(session: Session, verification_id: str) -> LearningObservation | None:
    run = session.get(VerificationRun, verification_id)
    if not run:
        rows = list(
            session.scalars(
                select(VerificationRun).where(VerificationRun.id.startswith(verification_id))
            ).all()
        )
        if len(rows) != 1:
            return None
        run = rows[0]

    # Dedup by verification
    existing = session.scalar(
        select(LearningObservation).where(
            LearningObservation.source_verification_id == run.id,
            LearningObservation.excluded.is_(False),
        )
    )
    if existing:
        return existing

    # Prefer primary+ for training; still ingest early with quality flag
    feature, outcome = build_vectors_from_verification(run, session)
    excluded, reason, flags = quality_check(feature, outcome, verification_status=run.status)
    if run.stage == "early":
        flags["stage_early"] = True

    conf = 0.55
    if run.stage in {"primary", "long_term"} and run.status == "verified":
        conf = 0.85
    elif run.status == "early_result":
        conf = 0.45

    obs = LearningObservation(
        id=str(uuid4()),
        content_id=run.content_id,
        publication_id=run.publication_id,
        prediction_ref=run.prediction_ref,
        source_verification_id=run.id,
        feature_vector=feature,
        outcome_vector=outcome,
        quality_flags=flags or None,
        confidence=conf,
        excluded=excluded,
        exclude_reason=reason,
        created_at=datetime.now(timezone.utc),
    )
    session.add(obs)
    session.flush()

    get_bus().publish(
        EventType.LEARNING_OBSERVATION_CREATED,
        {
            "observation_id": obs.id,
            "verification_id": run.id,
            "excluded": excluded,
            "character": feature.get("character"),
            "platform": feature.get("platform"),
        },
        producer="learning-engine",
    )
    return obs


def seed_observation(
    session: Session,
    *,
    feature_vector: dict[str, Any],
    outcome_vector: dict[str, Any],
    confidence: float = 0.8,
    content_id: str | None = None,
    publication_id: str | None = None,
    prediction_ref: str | None = None,
) -> LearningObservation:
    excluded, reason, flags = quality_check(
        feature_vector, outcome_vector, verification_status="verified"
    )
    obs = LearningObservation(
        id=str(uuid4()),
        content_id=content_id,
        publication_id=publication_id,
        prediction_ref=prediction_ref,
        feature_vector=feature_vector,
        outcome_vector=outcome_vector,
        quality_flags=flags or None,
        confidence=confidence,
        excluded=excluded,
        exclude_reason=reason,
        created_at=datetime.now(timezone.utc),
    )
    session.add(obs)
    session.flush()
    get_bus().publish(
        EventType.LEARNING_OBSERVATION_CREATED,
        {"observation_id": obs.id, "seeded": True},
        producer="learning-engine",
    )
    return obs


def list_observations(
    session: Session,
    *,
    include_excluded: bool = False,
    character: str | None = None,
    platform: str | None = None,
    limit: int = 500,
) -> list[LearningObservation]:
    stmt = select(LearningObservation).order_by(LearningObservation.created_at.desc()).limit(limit)
    if not include_excluded:
        stmt = stmt.where(LearningObservation.excluded.is_(False))
    rows = list(session.scalars(stmt).all())
    out = []
    for r in rows:
        f = r.feature_vector or {}
        if character and str(f.get("character") or "") != character:
            continue
        if platform and str(f.get("platform") or "") != platform:
            continue
        out.append(r)
    return out
