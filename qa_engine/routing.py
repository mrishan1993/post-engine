from __future__ import annotations

from qa_engine.schemas import QaIssueSpec, RecommendedAction


# Deterministic owner routing for common issue codes
ISSUE_ROUTING: dict[str, tuple[str, RecommendedAction]] = {
    "MISSING_FILE": ("assembly", "block"),
    "INVALID_RESOLUTION": ("assembly", "repair"),
    "INVALID_FPS": ("assembly", "repair"),
    "INVALID_DURATION": ("assembly", "repair"),
    "MISSING_AUDIO": ("assembly", "regenerate"),
    "AV_SYNC_FAILURE": ("assembly", "regenerate"),
    "BLACK_FRAME": ("video_generation", "regenerate"),
    "VIDEO_FROZEN": ("video_generation", "regenerate"),
    "CORRUPT_MEDIA": ("assembly", "block"),
    "ASPECT_RATIO_MISMATCH": ("assembly", "repair"),
    "VISUAL_ARTIFACT": ("video_generation", "regenerate"),
    "CHARACTER_DRIFT": ("video_generation", "regenerate"),
    "CANON_VIOLATION": ("storyboard", "regenerate"),
    "STORY_FIDELITY_FAILURE": ("story", "regenerate"),
    "STORYBOARD_MISMATCH": ("storyboard", "regenerate"),
    "VOICE_QUALITY": ("voice_generation", "regenerate"),
    "DIALOGUE_MISMATCH": ("voice_generation", "regenerate"),
    "MUSIC_EMOTIONAL_MISMATCH": ("music_sfx", "regenerate"),
    "MUSIC_TOO_LOUD": ("assembly", "repair"),
    "SFX_SYNC_FAILURE": ("assembly", "repair"),
    "DUCKING_FAILURE": ("assembly", "repair"),
    "CAPTION_MISMATCH": ("assembly", "repair"),
    "CAPTION_TIMING": ("assembly", "repair"),
    "CAPTION_SAFE_ZONE": ("assembly", "repair"),
    "CTA_TIMING": ("assembly", "repair"),
    "PLATFORM_CONSTRAINT": ("assembly", "repair"),
    "POLICY_VIOLATION": ("safety", "block"),
    "UNKNOWN_PROVENANCE": ("asset", "block"),
    "PREDICTED_QUALITY_LOW": ("probability", "review"),
}


def route_issue(issue: QaIssueSpec) -> QaIssueSpec:
    if issue.owner_engine and issue.recommended_action != "none":
        return issue
    owner, action = ISSUE_ROUTING.get(issue.code, ("qa", "review"))
    if not issue.owner_engine:
        issue.owner_engine = owner
    if issue.recommended_action == "none":
        # Infer from severity if routing says none-ish
        if issue.severity in {"critical", "high"}:
            issue.recommended_action = action
        elif issue.severity == "medium":
            issue.recommended_action = action if action != "none" else "repair"
        else:
            issue.recommended_action = "none"
    return issue


def repair_actions_from_issues(issues: list[QaIssueSpec]) -> list[dict]:
    actions = []
    for issue in issues:
        if issue.recommended_action != "repair":
            continue
        actions.append(
            {
                "code": issue.code,
                "owner_engine": issue.owner_engine or "assembly",
                "scene_id": issue.scene_id,
                "artifact_id": issue.artifact_id,
                "message": issue.message,
            }
        )
    return actions


def regeneration_targets_from_issues(issues: list[QaIssueSpec]) -> list[dict]:
    targets = []
    seen = set()
    for issue in issues:
        if issue.recommended_action != "regenerate":
            continue
        key = (issue.owner_engine, issue.scene_id, issue.artifact_id, issue.code)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            {
                "code": issue.code,
                "owner_engine": issue.owner_engine or "video_generation",
                "scene_id": issue.scene_id,
                "artifact_id": issue.artifact_id,
                "message": issue.message,
            }
        )
    return targets
