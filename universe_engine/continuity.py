from __future__ import annotations

import re
from typing import Any


FIRST_MEET_PATTERNS = [
    re.compile(r"\bmeets?\s+.+\s+for\s+the\s+first\s+time\b", re.I),
    re.compile(r"\bfirst\s+meeting\b", re.I),
    re.compile(r"\bnever\s+met\b", re.I),
    re.compile(r"\bstrangers?\b", re.I),
]


def detect_first_meet_claim(premise: str) -> bool:
    return any(p.search(premise) for p in FIRST_MEET_PATTERNS)


def behavioral_conflict(
    rules: list[str],
    actions: list[str],
) -> list[dict[str, Any]]:
    """Soft check: would this character actually do this?"""
    issues: list[dict[str, Any]] = []
    rules_l = [r.lower() for r in rules]
    for action in actions:
        a = action.lower()
        if any("avoid" in r and "confront" in r for r in rules_l):
            if any(w in a for w in ("fight", "confront", "attack", "physical confrontation")):
                issues.append(
                    {
                        "conflict_type": "behavioral",
                        "severity": "warning",
                        "description": "BEHAVIORAL_CONFLICT: character avoids confrontation",
                        "proposed": {"action": action},
                        "existing": {"rules": rules},
                        "suggested_revision": "Rewrite action to use humor/avoidance instead of confrontation",
                    }
                )
        if any("never lies about family" in r for r in rules_l):
            if "lie" in a and "family" in a:
                issues.append(
                    {
                        "conflict_type": "behavioral",
                        "severity": "fail",
                        "description": "BEHAVIORAL_CONFLICT: never lies about family",
                        "proposed": {"action": action},
                        "existing": {"rules": rules},
                        "suggested_revision": "Remove family-related lie",
                    }
                )
    return issues


def canon_predicate_conflict(
    existing: list[dict[str, Any]],
    subject: str,
    predicate: str,
    obj: str,
) -> dict[str, Any] | None:
    """Detect conflicting canon facts for same subject+predicate with different object."""
    for fact in existing:
        if fact.get("status") not in {"canon", "provisional"}:
            continue
        if (
            fact.get("subject", "").lower() == subject.lower()
            and fact.get("predicate", "").lower() == predicate.lower()
            and fact.get("object", "").lower() != obj.lower()
        ):
            return {
                "conflict_type": "canon",
                "severity": "fail",
                "description": f"Canon conflict: {subject} {predicate}",
                "proposed": {"subject": subject, "predicate": predicate, "object": obj},
                "existing": fact,
                "suggested_revision": "Retcon, mark alternate, or revise proposed fact",
            }
    return None


def score_memory_recall(
    *,
    importance: float,
    emotional_weight: float,
    recency: float,
) -> float:
    return round(min(1.0, 0.45 * importance + 0.35 * emotional_weight + 0.2 * recency), 3)
