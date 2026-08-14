from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from verification_engine.calibration import apply_calibration_updates
from verification_engine.context import (
    resolve_actual_snapshot,
    resolve_prediction_snapshot,
    stage_for_age,
    status_for_stage,
)
from verification_engine.diagnosis import build_learning_signals, diagnose
from verification_engine.metrics import (
    brier_score,
    extract_predicted_actual_pairs,
    log_loss,
    mape,
    verify_metric,
)
from verification_engine.schemas import (
    CreateVerificationRequest,
    LearningSignalOut,
    MetricVerification,
    PredictionSnapshot,
    RootCauseAnalysis,
    VerificationResultOut,
)
from db.models import LearningSignal, VerificationMetricResult, VerificationRun


class VerificationExecutor:
    def __init__(self, session: Session):
        self.session = session

    def process(self, run_id: str) -> VerificationRun:
        run = self.session.get(VerificationRun, run_id)
        if not run:
            raise ValueError("verification run not found")

        get_bus().publish(
            EventType.VERIFICATION_STARTED,
            {"verification_id": run.id, "prediction_ref": run.prediction_ref, "stage": run.stage},
            producer="verification-engine",
        )

        prediction = PredictionSnapshot.model_validate(run.prediction_snapshot)
        if not run.publication_id:
            run.status = "invalid"
            run.result_summary = {"error": "missing publication_id"}
            run.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            return run

        window_h = float((run.measurement_window or {}).get("window_hours") or prediction.target.window_hours)
        actual = resolve_actual_snapshot(
            self.session,
            publication_id=run.publication_id,
            window_hours=window_h,
            qa_score=(run.lineage or {}).get("qa_score"),
            actual_overrides=(run.actual_snapshot or {}).get("metrics")
            if run.actual_snapshot
            else None,
        )
        if not any(v is not None for v in (actual.metrics or {}).values()):
            run.status = "insufficient_data"
            run.actual_snapshot = actual.model_dump(mode="json")
            run.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            return run

        # Recompute stage from age if needed
        stage = run.stage or stage_for_age(actual.age_hours, prediction.target.window_hours)
        run.stage = stage

        pairs = extract_predicted_actual_pairs(prediction.model_dump(), actual.metrics)
        metric_outs = []
        abs_pct = []
        for metric, pred_v, act_v, thr in pairs:
            # Probability vs views threshold: binary outcome only (avoid nonsense APE)
            if metric == "viral_target" and thr is not None and act_v is not None and pred_v is not None:
                outcome = float(act_v) >= float(thr)
                mv = MetricVerification(
                    metric=metric,
                    predicted_value=round(float(pred_v), 6),
                    actual_value=round(float(act_v), 6),
                    absolute_error=None,
                    relative_error=None,
                    log_error=None,
                    outcome=outcome,
                    bias_direction="unknown",
                )
            else:
                binary_thr = None
                if metric == "virality" and act_v is not None:
                    binary_thr = 0.7
                mv = verify_metric(metric, pred_v, act_v, binary_threshold=binary_thr)
            metric_outs.append(mv)
            if mv.relative_error is not None:
                abs_pct.append(abs(mv.relative_error) * 100.0)

            self.session.add(
                VerificationMetricResult(
                    id=str(uuid4()),
                    verification_run_id=run.id,
                    metric=mv.metric,
                    predicted_value=mv.predicted_value,
                    actual_value=mv.actual_value,
                    absolute_error=mv.absolute_error,
                    relative_error=mv.relative_error,
                    log_error=mv.log_error,
                    outcome=mv.outcome,
                    metadata_json={"bias_direction": mv.bias_direction},
                )
            )

        # Brier / log loss on viral_target or virality
        binary = next((m for m in metric_outs if m.metric in {"viral_target", "virality"} and m.outcome is not None), None)
        brier = logloss = None
        confidence_label = "unknown"
        if binary and binary.predicted_value is not None and binary.outcome is not None:
            brier = brier_score(float(binary.predicted_value), bool(binary.outcome))
            logloss = log_loss(float(binary.predicted_value), bool(binary.outcome))
            p = float(binary.predicted_value)
            if binary.outcome and p >= 0.5:
                confidence_label = "correct"
            elif (not binary.outcome) and p < 0.5:
                confidence_label = "correct"
            elif binary.outcome and p < 0.5:
                confidence_label = "underconfident"
            elif (not binary.outcome) and p >= 0.7:
                confidence_label = "overconfident"
            else:
                confidence_label = "incorrect"

        diagnosis = diagnose(
            prediction,
            actual,
            metric_rows=[m.model_dump() for m in metric_outs],
        )
        learning = build_learning_signals(
            prediction,
            actual,
            metric_rows=[m.model_dump() for m in metric_outs],
            diagnosis=diagnosis,
            confidence_label=confidence_label,
        )
        for sig in learning:
            self.session.add(
                LearningSignal(
                    id=str(uuid4()),
                    content_id=prediction.content_id or run.content_id,
                    prediction_ref=run.prediction_ref,
                    verification_id=run.id,
                    signal_type=sig["signal_type"],
                    signal_value=sig["signal_value"],
                    confidence=sig.get("confidence"),
                )
            )
            get_bus().publish(
                EventType.LEARNING_SIGNAL_CREATED,
                {
                    "verification_id": run.id,
                    "signal_type": sig["signal_type"],
                    "prediction_ref": run.prediction_ref,
                },
                producer="verification-engine",
            )

        apply_calibration_updates(
            self.session,
            model_id=prediction.model_id,
            model_version=prediction.model_version,
            metrics=metric_outs,
            segments=prediction.segments,
        )
        get_bus().publish(
            EventType.CALIBRATION_UPDATED,
            {
                "model_id": prediction.model_id,
                "model_version": prediction.model_version,
                "verification_id": run.id,
            },
            producer="verification-engine",
        )

        # Bridge to legacy registry verification when possible
        if prediction.registry_prediction_id is not None:
            try:
                from prediction.verification import verify_prediction as legacy_verify

                legacy_verify(
                    self.session,
                    prediction.registry_prediction_id,
                    {
                        "views": actual.metrics.get("views"),
                        "shares": actual.metrics.get("shares"),
                        "saves": actual.metrics.get("saves"),
                        "comments": actual.metrics.get("comments"),
                        "engagement_rate": actual.metrics.get("engagement_rate"),
                        "retention": actual.metrics.get("completion_rate"),
                        "followers": actual.metrics.get("followers_gained"),
                    },
                )
            except Exception:  # noqa: BLE001
                pass

        run.actual_snapshot = actual.model_dump(mode="json")
        run.diagnosis = diagnosis.model_dump()
        run.status = status_for_stage(stage, has_actuals=True)
        run.result_summary = {
            "brier_score": brier,
            "log_loss": logloss,
            "mape": mape(abs_pct),
            "confidence_label": confidence_label,
            "metric_count": len(metric_outs),
            "prediction_quality_version": "v1",
        }
        run.completed_at = datetime.now(timezone.utc)
        self.session.flush()

        evt = EventType.PRIMARY_VERIFICATION_COMPLETED
        if stage == "early":
            evt = EventType.EARLY_VERIFICATION_COMPLETED
        elif stage == "long_term":
            evt = EventType.LONG_TERM_VERIFICATION_COMPLETED
        get_bus().publish(
            evt,
            {
                "verification_id": run.id,
                "prediction_ref": run.prediction_ref,
                "status": run.status,
                "confidence_label": confidence_label,
                "brier_score": brier,
            },
            producer="verification-engine",
        )
        if confidence_label == "correct":
            get_bus().publish(
                EventType.PREDICTION_CORRECT,
                {"verification_id": run.id, "prediction_ref": run.prediction_ref},
                producer="verification-engine",
            )
        elif confidence_label in {"incorrect", "overconfident", "underconfident"}:
            get_bus().publish(
                EventType.PREDICTION_INCORRECT,
                {
                    "verification_id": run.id,
                    "prediction_ref": run.prediction_ref,
                    "label": confidence_label,
                },
                producer="verification-engine",
            )
            if confidence_label == "overconfident":
                get_bus().publish(
                    EventType.PREDICTION_OVERCONFIDENT,
                    {"verification_id": run.id, "prediction_ref": run.prediction_ref},
                    producer="verification-engine",
                )
            if confidence_label == "underconfident":
                get_bus().publish(
                    EventType.PREDICTION_UNDERCONFIDENT,
                    {"verification_id": run.id, "prediction_ref": run.prediction_ref},
                    producer="verification-engine",
                )

        # Soft handoff → Learning & Optimization (non-fatal)
        try:
            from learning_engine.service import LearningService

            LearningService(self.session).from_verification_hook(run.id)
        except Exception:  # noqa: BLE001
            pass

        return run


def create_run_from_request(session: Session, req: CreateVerificationRequest) -> VerificationRun:
    prediction = resolve_prediction_snapshot(
        session,
        prediction=req.prediction,
        prediction_ref=req.prediction_ref,
        registry_prediction_id=req.registry_prediction_id,
        publication_id=req.publication_id,
    )
    window_h = req.measurement_window_hours or prediction.target.window_hours
    run = VerificationRun(
        id=str(uuid4()),
        prediction_ref=prediction.id,
        registry_prediction_id=prediction.registry_prediction_id or req.registry_prediction_id,
        publication_id=req.publication_id,
        content_id=prediction.content_id,
        stage=req.stage,
        status="pending",
        measurement_window={"window_hours": window_h},
        prediction_snapshot=prediction.model_dump(mode="json"),
        actual_snapshot={"metrics": req.actuals} if req.actuals else None,
        model_id=prediction.model_id,
        model_version=prediction.model_version,
        lineage={"qa_score": req.qa_score},
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    return run


def to_result_out(run: VerificationRun, session: Session) -> VerificationResultOut:
    from sqlalchemy import select

    rows = list(
        session.scalars(
            select(VerificationMetricResult).where(
                VerificationMetricResult.verification_run_id == run.id
            )
        ).all()
    )
    signals = list(
        session.scalars(
            select(LearningSignal).where(LearningSignal.verification_id == run.id)
        ).all()
    )
    summary = run.result_summary or {}
    metrics_out: list[MetricVerification] = []
    for r in rows:
        meta = r.metadata_json or {}
        metrics_out.append(
            MetricVerification(
                metric=r.metric,
                predicted_value=float(r.predicted_value) if r.predicted_value is not None else None,
                actual_value=float(r.actual_value) if r.actual_value is not None else None,
                absolute_error=float(r.absolute_error) if r.absolute_error is not None else None,
                relative_error=float(r.relative_error) if r.relative_error is not None else None,
                log_error=float(r.log_error) if r.log_error is not None else None,
                outcome=r.outcome,
                bias_direction=meta.get("bias_direction") or "unknown",
            )
        )
    return VerificationResultOut(
        verification_id=run.id,
        prediction_ref=run.prediction_ref,
        publication_id=run.publication_id,
        stage=run.stage,
        status=run.status,
        metrics=metrics_out,
        brier_score=summary.get("brier_score"),
        log_loss=summary.get("log_loss"),
        mape=summary.get("mape"),
        confidence_label=summary.get("confidence_label") or "unknown",
        diagnosis=RootCauseAnalysis.model_validate(run.diagnosis) if run.diagnosis else None,
        learning_signals=[
            LearningSignalOut(
                signal_type=s.signal_type,
                signal_value=s.signal_value,
                confidence=float(s.confidence or 0.5),
            )
            for s in signals
        ],
        summary=summary,
    )
