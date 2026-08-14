from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from verification_engine.calibration import list_calibration
from verification_engine.executor import (
    VerificationExecutor,
    create_run_from_request,
    to_result_out,
)
from verification_engine.metrics import spearman_rank
from verification_engine.schemas import (
    CompareModelsRequest,
    CreateVerificationRequest,
    VerificationResultOut,
)
from db.models import LearningSignal, VerificationRun


class VerificationService:
    def __init__(self, session: Session):
        self.session = session
        self.executor = VerificationExecutor(session)

    def create_run(self, request: CreateVerificationRequest | dict[str, Any]) -> VerificationResultOut:
        req = (
            request
            if isinstance(request, CreateVerificationRequest)
            else CreateVerificationRequest.model_validate(request)
        )
        run = create_run_from_request(self.session, req)
        if req.process:
            run = self.executor.process(run.id)
        return to_result_out(run, self.session)

    def process(self, verification_id: str) -> VerificationResultOut:
        run = self._get_run(verification_id)
        run = self.executor.process(run.id)
        return to_result_out(run, self.session)

    def get(self, verification_id: str) -> VerificationResultOut:
        return to_result_out(self._get_run(verification_id), self.session)

    def get_by_prediction(self, prediction_ref: str) -> list[VerificationResultOut]:
        rows = list(
            self.session.scalars(
                select(VerificationRun)
                .where(VerificationRun.prediction_ref == prediction_ref)
                .order_by(VerificationRun.created_at.desc())
            ).all()
        )
        return [to_result_out(r, self.session) for r in rows]

    def calibration(
        self,
        model_id: str,
        *,
        model_version: str | None = None,
        metric: str = "viral_target",
    ) -> list[dict[str, Any]]:
        return list_calibration(
            self.session,
            model_id=model_id,
            model_version=model_version,
            metric=metric,
        )

    def model_performance(
        self,
        model_id: str,
        *,
        model_version: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(VerificationRun).where(VerificationRun.model_id == model_id)
        if model_version:
            stmt = stmt.where(VerificationRun.model_version == model_version)
        runs = list(self.session.scalars(stmt).all())
        briers: list[float] = []
        loglosses: list[float] = []
        pred_rank: list[float] = []
        act_rank: list[float] = []
        for run in runs:
            summary = run.result_summary or {}
            if summary.get("brier_score") is not None:
                briers.append(float(summary["brier_score"]))
            if summary.get("log_loss") is not None:
                loglosses.append(float(summary["log_loss"]))
            snap = run.prediction_snapshot or {}
            preds = snap.get("predictions") or {}
            vir = preds.get("virality") or {}
            p = vir.get("probability") if isinstance(vir, dict) else vir
            actual = (run.actual_snapshot or {}).get("metrics") or {}
            views = actual.get("views")
            if p is not None and views is not None:
                pred_rank.append(float(p))
                act_rank.append(float(views))

        buckets = list_calibration(
            self.session, model_id=model_id, model_version=model_version, metric="viral_target"
        )
        cal_errs = [abs(b["calibration_error"]) for b in buckets if b.get("sample_count", 0) > 0]
        return {
            "model_id": model_id,
            "model_version": model_version,
            "run_count": len(runs),
            "mean_brier": sum(briers) / len(briers) if briers else None,
            "mean_log_loss": sum(loglosses) / len(loglosses) if loglosses else None,
            "mean_abs_calibration_error": sum(cal_errs) / len(cal_errs) if cal_errs else None,
            "spearman_ranking": spearman_rank(pred_rank, act_rank),
            "buckets": buckets,
        }

    def learning_signals(
        self,
        *,
        prediction_ref: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = select(LearningSignal).order_by(LearningSignal.created_at.desc()).limit(limit)
        if prediction_ref:
            stmt = select(LearningSignal).where(
                LearningSignal.prediction_ref == prediction_ref
            ).order_by(LearningSignal.created_at.desc()).limit(limit)
        rows = list(self.session.scalars(stmt).all())
        return [
            {
                "id": r.id,
                "content_id": r.content_id,
                "prediction_ref": r.prediction_ref,
                "verification_id": r.verification_id,
                "signal_type": r.signal_type,
                "signal_value": r.signal_value,
                "confidence": float(r.confidence or 0),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def compare_models(self, request: CompareModelsRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, CompareModelsRequest)
            else CompareModelsRequest.model_validate(request)
        )
        # model_a / model_b as "id:version" or just id
        def split(key: str) -> tuple[str, str | None]:
            if ":" in key:
                mid, ver = key.split(":", 1)
                return mid, ver
            return key, None

        a_id, a_ver = split(req.model_a)
        b_id, b_ver = split(req.model_b)
        return {
            "metric": req.metric,
            "champion": self.model_performance(a_id, model_version=a_ver),
            "challenger": self.model_performance(b_id, model_version=b_ver),
            "note": "Compare calibration/Brier/ranking before promotion; do not auto-promote.",
        }

    def verify_from_performance(
        self,
        publication_id: str,
        *,
        stage: str | None = None,
        simulate_age_hours: float | None = None,
    ) -> VerificationResultOut | None:
        """Soft entrypoint for Performance Engine hook — never raises to caller."""
        from verification_engine.context import stage_for_age

        try:
            from db.models import PostAnalytics, PublicationReceipt

            receipt = self.session.get(PublicationReceipt, publication_id)
            if not receipt:
                return None
            analytics = self.session.get(PostAnalytics, receipt.id)
            link = (analytics.prediction_link if analytics else None) or {}

            age_h = simulate_age_hours
            if age_h is None and receipt.published_at:
                from datetime import datetime, timezone

                pub = receipt.published_at
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                age_h = (datetime.now(timezone.utc) - pub).total_seconds() / 3600.0

            window = 48.0
            st = stage or stage_for_age(age_h, window)
            # Dedup: skip if same stage already verified recently for this pub
            existing = self.session.scalar(
                select(VerificationRun).where(
                    VerificationRun.publication_id == receipt.id,
                    VerificationRun.stage == st,
                    VerificationRun.status.in_(["verified", "early_result"]),
                )
            )
            if existing:
                return to_result_out(existing, self.session)

            pred_payload = None
            if link.get("predictions") or link.get("virality") is not None:
                pred_payload = {
                    "id": str(
                        analytics.prediction_id
                        if analytics and analytics.prediction_id
                        else (receipt.lineage or {}).get("prediction_id")
                        or f"link_{receipt.id[:8]}"
                    ),
                    "content_id": receipt.content_id,
                    "model_id": str(link.get("model_id") or "virality_predictor"),
                    "model_version": str(link.get("model_version") or "rule_v1"),
                    "predictions": link.get("predictions")
                    or {
                        "virality": {"probability": float(link.get("virality", 0.7))},
                        "engagement": {"probability": float(link.get("engagement", 0.7))},
                        "completion": {"probability": float(link.get("completion", 0.65))},
                        "views": {"expected": float(link.get("views", 1_000_000))},
                        "share_rate": {"expected": float(link.get("share_rate", 0.03))},
                    },
                    "confidence": {"overall": float(link.get("confidence", 0.75))},
                    "target": link.get("target")
                    or {"metric": "views", "threshold": 1_000_000, "window_hours": 48},
                    "signals": link.get("signals") or {},
                    "segments": {
                        "platform": receipt.platform or "unknown",
                        "character": str(
                            ((analytics.content_fingerprint if analytics else None) or {}).get(
                                "character"
                            )
                            or (receipt.lineage or {}).get("character_slug")
                            or ""
                        ),
                    },
                }

            return self.create_run(
                CreateVerificationRequest(
                    publication_id=receipt.id,
                    prediction=pred_payload,
                    prediction_ref=(receipt.lineage or {}).get("prediction_id"),
                    stage=st,  # type: ignore[arg-type]
                    process=True,
                )
            )
        except Exception:  # noqa: BLE001
            return None

    def _get_run(self, verification_id: str) -> VerificationRun:
        row = self.session.get(VerificationRun, verification_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(VerificationRun).where(VerificationRun.id.startswith(verification_id))
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("verification run not found")
        return rows[0]
