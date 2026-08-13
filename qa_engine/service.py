from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from qa_engine.bridge import approval_gate_from_qa_run
from qa_engine.context import resolve_qa_package
from qa_engine.executor import QAExecutor
from qa_engine.schemas import (
    CreateQaRunRequest,
    HumanReviewRequest,
    QaPackage,
    QaThresholds,
)
from qa_engine.state import transition_run
from db.models import QaIssue, QaMeasurement, QaRun


class QAService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, request: CreateQaRunRequest | dict[str, Any]) -> QaRun:
        req = (
            request
            if isinstance(request, CreateQaRunRequest)
            else CreateQaRunRequest.model_validate(request)
        )
        thresholds = (
            req.thresholds
            if isinstance(req.thresholds, QaThresholds)
            else QaThresholds.model_validate(req.thresholds or {})
        )
        base_pkg = None
        if req.package:
            base_pkg = (
                req.package
                if isinstance(req.package, QaPackage)
                else QaPackage.model_validate(req.package)
            )
        package = resolve_qa_package(
            self.session,
            content_id=req.content_id or (base_pkg.content_id if base_pkg else None),
            assembly_id=req.assembly_id or (base_pkg.assembly_id if base_pkg else None),
            artifact_id=req.artifact_id or (base_pkg.artifact_id if base_pkg else None),
            storage_uri=req.storage_uri or (base_pkg.storage_uri if base_pkg else None),
            character_slug=req.character_slug,
            prediction=req.prediction or (base_pkg.prediction if base_pkg else {}),
            target_platforms=req.target_platforms,
            force_safety_risk=req.force_safety_risk,
            injected_issues=req.injected_issues or (base_pkg.injected_issues if base_pkg else []),
            package=base_pkg,
        )
        if not package.storage_uri and not package.assembly_id and not package.specification:
            raise ValueError("assembly_id, artifact/storage_uri, or package required")

        version = self._next_version(package.content_id)
        run = QaRun(
            id=str(uuid4()),
            content_id=package.content_id,
            assembly_id=package.assembly_id,
            artifact_id=package.artifact_id,
            version=version,
            status="queued",
            lineage=package.lineage,
            thresholds=thresholds.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()

        if req.process:
            return QAExecutor(self.session).process(run.id, package, thresholds)
        return run

    def get(self, qa_run_id: str) -> QaRun | None:
        try:
            return self._get_run(qa_run_id)
        except ValueError:
            return None

    def list_issues(self, qa_run_id: str) -> list[QaIssue]:
        run = self._get_run(qa_run_id)
        return list(
            self.session.scalars(select(QaIssue).where(QaIssue.qa_run_id == run.id)).all()
        )

    def list_measurements(self, qa_run_id: str) -> list[QaMeasurement]:
        run = self._get_run(qa_run_id)
        return list(
            self.session.scalars(
                select(QaMeasurement).where(QaMeasurement.qa_run_id == run.id)
            ).all()
        )

    def approve(self, qa_run_id: str, reviewer: str = "human", notes: str | None = None) -> QaRun:
        run = self._get_run(qa_run_id)
        if run.decision == "block":
            raise ValueError("cannot approve a BLOCK decision without remediation")
        run.human_review = {
            "decision": "approve",
            "reviewer": reviewer,
            "notes": notes,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        # Human override to pass for publishing bridge
        result = dict(run.result or {})
        result["decision"] = "pass"
        result["human_override"] = True
        run.result = result
        run.decision = "pass"
        if run.status == "review_required":
            run.status = transition_run("review_required", "completed")
        self.session.flush()
        get_bus().publish(
            EventType.QA_APPROVED,
            {"qa_run_id": run.id, "reviewer": reviewer, "content_id": run.content_id},
            producer="qa-engine",
        )
        return run

    def reject(
        self,
        qa_run_id: str,
        reviewer: str = "human",
        reasons: list[str] | None = None,
        notes: str | None = None,
    ) -> QaRun:
        run = self._get_run(qa_run_id)
        run.human_review = {
            "decision": "reject",
            "reviewer": reviewer,
            "reasons": reasons or [],
            "notes": notes,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        result = dict(run.result or {})
        result["decision"] = "block"
        result["human_override"] = True
        run.result = result
        run.decision = "block"
        if run.status == "review_required":
            run.status = transition_run("review_required", "completed")
        self.session.flush()
        get_bus().publish(
            EventType.QA_REJECTED,
            {
                "qa_run_id": run.id,
                "reviewer": reviewer,
                "reasons": reasons or [],
                "content_id": run.content_id,
            },
            producer="qa-engine",
        )
        return run

    def review(self, qa_run_id: str, request: HumanReviewRequest | dict[str, Any]) -> QaRun:
        req = (
            request
            if isinstance(request, HumanReviewRequest)
            else HumanReviewRequest.model_validate(request)
        )
        if req.decision == "approve":
            return self.approve(qa_run_id, reviewer=req.reviewer, notes=req.notes)
        if req.decision == "reject":
            return self.reject(
                qa_run_id, reviewer=req.reviewer, reasons=req.reasons, notes=req.notes
            )
        run = self._get_run(qa_run_id)
        run.human_review = req.model_dump()
        if req.decision == "regenerate":
            run.decision = "regenerate"
            get_bus().publish(
                EventType.QA_REGENERATION_REQUESTED,
                {"qa_run_id": run.id, "reviewer": req.reviewer, "manual": True},
                producer="qa-engine",
            )
        self.session.flush()
        return run

    def request_repair(self, qa_run_id: str) -> dict[str, Any]:
        run = self._get_run(qa_run_id)
        actions = (run.result or {}).get("repair_actions") or []
        get_bus().publish(
            EventType.QA_REPAIR_REQUESTED,
            {"qa_run_id": run.id, "actions": actions, "manual": True},
            producer="qa-engine",
        )
        return {"qa_run_id": run.id, "actions": actions}

    def request_regenerate(self, qa_run_id: str) -> dict[str, Any]:
        run = self._get_run(qa_run_id)
        targets = (run.result or {}).get("regeneration_targets") or []
        get_bus().publish(
            EventType.QA_REGENERATION_REQUESTED,
            {"qa_run_id": run.id, "targets": targets, "manual": True},
            producer="qa-engine",
        )
        return {"qa_run_id": run.id, "targets": targets}

    def to_publishing_approval(self, qa_run_id: str) -> dict[str, Any]:
        run = self._get_run(qa_run_id)
        return approval_gate_from_qa_run(run)

    def _get_run(self, qa_run_id: str) -> QaRun:
        row = self.session.get(QaRun, qa_run_id)
        if row:
            return row
        rows = list(
            self.session.scalars(select(QaRun).where(QaRun.id.startswith(qa_run_id))).all()
        )
        if len(rows) != 1:
            raise ValueError("qa run not found")
        return rows[0]

    def _next_version(self, content_id: str) -> int:
        rows = list(
            self.session.scalars(select(QaRun).where(QaRun.content_id == content_id)).all()
        )
        if not rows:
            return 1
        return max(int(r.version) for r in rows) + 1
