from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from qa_engine.checkers import (
    run_audio_qa,
    run_caption_qa,
    run_character_qa,
    run_platform_qa,
    run_predictive_qa,
    run_safety_qa,
    run_story_qa,
    run_storyboard_qa,
    run_technical_qa,
    run_visual_qa,
)
from qa_engine.decision import decide
from qa_engine.schemas import DimensionResult, QaPackage, QaResult, QaThresholds
from qa_engine.state import transition_run
from db.models import QaIssue, QaMeasurement, QaRun

# Dimension event map for observability
_DIMENSION_EVENTS = {
    "technical": EventType.TECHNICAL_QA_COMPLETED,
    "visual": EventType.VISUAL_QA_COMPLETED,
    "audio": EventType.AUDIO_QA_COMPLETED,
    "character": EventType.CHARACTER_QA_COMPLETED,
    "story": EventType.STORY_QA_COMPLETED,
    "captions": EventType.CAPTION_QA_COMPLETED,
    "platform": EventType.PLATFORM_QA_COMPLETED,
    "safety": EventType.SAFETY_QA_COMPLETED,
}


class QAExecutor:
    def __init__(self, session: Session):
        self.session = session

    def process(self, qa_run_id: str, package: QaPackage, thresholds: QaThresholds) -> QaRun:
        run = self.session.get(QaRun, qa_run_id)
        if not run:
            raise ValueError("qa run not found")

        run.status = transition_run(run.status, "running")
        run.started_at = datetime.now(timezone.utc)
        self.session.flush()
        get_bus().publish(
            EventType.QA_RUN_STARTED,
            {"qa_run_id": run.id, "content_id": run.content_id, "assembly_id": run.assembly_id},
            producer="qa-engine",
        )

        checkers = [
            ("technical", run_technical_qa),
            ("visual", run_visual_qa),
            ("audio", run_audio_qa),
            ("character", run_character_qa),
            ("story", run_story_qa),
            ("storyboard", run_storyboard_qa),
            ("captions", run_caption_qa),
            ("platform", run_platform_qa),
            ("safety", run_safety_qa),
            ("predicted_quality", run_predictive_qa),
        ]

        dimension_results: list[DimensionResult] = []
        # Cascade: if technical critically fails missing file, skip expensive dims conceptually
        # but still run cheap deterministic ones for complete report
        tech_first = run_technical_qa(package, thresholds)
        dimension_results.append(tech_first)
        self._emit_dimension(run.id, tech_first)
        skip_heavy = any(i.code == "MISSING_FILE" for i in tech_first.issues)

        for name, fn in checkers[1:]:
            if skip_heavy and name in {"visual", "character", "story", "storyboard"}:
                dimension_results.append(
                    DimensionResult(
                        dimension=name,
                        score=0.0,
                        passed=False,
                        skipped=True,
                        notes=["skipped due to missing final artifact"],
                    )
                )
                continue
            result = fn(package, thresholds)
            dimension_results.append(result)
            self._emit_dimension(run.id, result)

        scores = {d.dimension: d.score for d in dimension_results}
        all_issues = []
        all_measurements = []
        for d in dimension_results:
            all_issues.extend(d.issues)
            all_measurements.extend(d.measurements)

        # policy risk from safety measurements
        policy_risk = "none"
        for m in all_measurements:
            if m.dimension == "safety" and m.metric == "policy_risk":
                policy_risk = str((m.metadata or {}).get("risk") or "none")
        if package.force_safety_risk:
            policy_risk = package.force_safety_risk

        result = decide(
            content_id=package.content_id,
            dimension_scores=scores,
            issues=all_issues,
            thresholds=thresholds,
            policy_risk=policy_risk,
        )
        result.measurements = all_measurements
        result.generated_at = datetime.now(timezone.utc)

        # Persist issues + measurements
        for issue in result.issues:
            self.session.add(
                QaIssue(
                    id=str(uuid4()),
                    qa_run_id=run.id,
                    issue_code=issue.code,
                    severity=issue.severity,
                    category=issue.category,
                    artifact_id=issue.artifact_id,
                    scene_id=issue.scene_id,
                    timestamp_sec=issue.timestamp_sec,
                    score=issue.score,
                    description=issue.message,
                    owner_engine=issue.owner_engine,
                    recommended_action=issue.recommended_action,
                    status="open",
                    metadata_json=issue.metadata,
                )
            )
        for m in result.measurements:
            self.session.add(
                QaMeasurement(
                    id=str(uuid4()),
                    qa_run_id=run.id,
                    dimension=m.dimension,
                    metric=m.metric,
                    value=m.value,
                    threshold=m.threshold,
                    passed=m.passed,
                    metadata_json=m.metadata,
                )
            )

        run.overall_score = result.overall_score
        run.dimension_scores = result.dimensions
        run.decision = result.decision
        run.result = result.model_dump(mode="json")
        run.completed_at = datetime.now(timezone.utc)
        if result.decision == "review_required":
            run.status = transition_run("running", "review_required")
            get_bus().publish(
                EventType.QA_REVIEW_REQUIRED,
                {
                    "qa_run_id": run.id,
                    "decision": result.decision,
                    "policy_risk": result.policy_risk,
                    "overall_score": result.overall_score,
                },
                producer="qa-engine",
            )
        else:
            run.status = transition_run("running", "completed")

        self.session.flush()
        get_bus().publish(
            EventType.QA_RUN_COMPLETED,
            {
                "qa_run_id": run.id,
                "content_id": run.content_id,
                "decision": run.decision,
                "overall_score": float(run.overall_score or 0),
                "issue_count": len(result.issues),
            },
            producer="qa-engine",
        )
        if result.decision == "repair":
            get_bus().publish(
                EventType.QA_REPAIR_REQUESTED,
                {"qa_run_id": run.id, "actions": result.repair_actions},
                producer="qa-engine",
            )
        if result.decision == "regenerate":
            get_bus().publish(
                EventType.QA_REGENERATION_REQUESTED,
                {"qa_run_id": run.id, "targets": result.regeneration_targets},
                producer="qa-engine",
            )
        return run

    def _emit_dimension(self, qa_run_id: str, result: DimensionResult) -> None:
        evt = _DIMENSION_EVENTS.get(result.dimension)
        if not evt:
            return
        get_bus().publish(
            evt,
            {
                "qa_run_id": qa_run_id,
                "dimension": result.dimension,
                "score": result.score,
                "passed": result.passed,
                "issue_count": len(result.issues),
                "skipped": result.skipped,
            },
            producer="qa-engine",
        )
