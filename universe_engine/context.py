from __future__ import annotations

from typing import Any


def rank_memories(
    memories: list[dict[str, Any]],
    *,
    limit: int,
    premise: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve relevant creative memory — not the entire universe dump."""
    premise_l = (premise or "").lower()
    scored = []
    for m in memories:
        base = float(m.get("recall_probability") or 0.5)
        text = (m.get("text") or "").lower()
        boost = 0.0
        if premise_l:
            overlap = sum(1 for w in premise_l.split() if len(w) > 3 and w in text)
            boost = min(0.3, 0.05 * overlap)
        scored.append((base + boost, m))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:limit]]


def build_visual_context(canonical: dict[str, Any]) -> dict[str, Any]:
    appearance = dict(canonical.get("appearance") or {})
    canon = canonical.get("canon") or {}
    return {
        "appearance": appearance,
        "immutable_traits": (canon.get("immutable") if isinstance(canon, dict) else None)
        or appearance.get("immutable_traits")
        or ["face", "facial_structure"],
        "mutable_traits": (canon.get("flexible") if isinstance(canon, dict) else None)
        or ["clothing", "accessories"],
        "visual_style": canonical.get("visual_style") or {},
    }


def build_voice_context(canonical: dict[str, Any]) -> dict[str, Any]:
    return dict(canonical.get("voice") or {})
