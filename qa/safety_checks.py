from __future__ import annotations

from typing import Any


def summarize_flags(safety_check_result: dict[str, Any] | None) -> str:
    if not safety_check_result:
        return "none"
    flags = safety_check_result.get("flags") or {}
    if not flags:
        return "none"
    return ", ".join(f"{k}: {v:.2f}" for k, v in flags.items())
