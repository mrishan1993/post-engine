from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db.models import QaRun


def approval_gate_from_qa_run(run: QaRun) -> dict[str, Any]:
    """Map QARun → Publishing ApprovalGate fields."""
    decision = (run.decision or "").lower()
    result = run.result or {}
    policy_risk = str(result.get("policy_risk") or "none")

    if decision == "pass":
        qa_status = "passed"
        approved = True
    elif decision == "block":
        qa_status = "failed"
        approved = False
    elif decision == "review_required":
        qa_status = "pending"
        approved = False
    else:
        # repair / regenerate — not publishable yet
        qa_status = "failed"
        approved = False

    return {
        "qa_status": qa_status,
        "approved": approved,
        "policy_risk": policy_risk,
        "reviewer": "qa-engine",
        "notes": f"qa_run={run.id} decision={decision} score={run.overall_score}",
        "approved_at": datetime.now(timezone.utc).isoformat() if approved else None,
        "qa_run_id": run.id,
        "overall_score": float(run.overall_score or 0),
        "decision": decision,
    }
