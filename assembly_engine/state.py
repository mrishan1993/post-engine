from __future__ import annotations


ASSEMBLY_ALLOWED: dict[str, set[str]] = {
    "draft": {"validated", "failed"},
    "validated": {"rendering", "draft", "failed"},
    "rendering": {"completed", "failed"},
    # Re-render (draft/preview/platform export) without inventing a new assembly version
    "completed": {"rendering"},
    "failed": {"draft", "validated", "rendering"},
}

RENDER_ALLOWED: dict[str, set[str]] = {
    "queued": {"validating", "cancelled"},
    "validating": {"resolving_assets", "failed"},
    "resolving_assets": {"building_timeline", "failed"},
    "building_timeline": {"rendering", "failed"},
    "rendering": {"validating_output", "failed", "retry"},
    "validating_output": {"completed", "failed"},
    "completed": set(),
    "retry": {"validating", "failed"},
    "failed": {"retry", "cancelled"},
    "cancelled": set(),
}


def can_transition(allowed: dict[str, set[str]], current: str, new: str) -> bool:
    if current == new:
        return True
    return new in allowed.get(current, set())


def transition_assembly(current: str, new: str) -> str:
    if not can_transition(ASSEMBLY_ALLOWED, current, new):
        raise ValueError(f"invalid assembly transition {current} → {new}")
    return new


def transition_render(current: str, new: str) -> str:
    if not can_transition(RENDER_ALLOWED, current, new):
        raise ValueError(f"invalid render transition {current} → {new}")
    return new
