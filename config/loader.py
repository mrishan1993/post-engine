from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from config.schema import VerticalConfig

ROOT = Path(__file__).resolve().parent.parent
VERTICALS_DIR = ROOT / "config" / "verticals"
GLOBAL_CONFIG_PATH = ROOT / "config" / "global.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data


def load_global_config(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml(path or GLOBAL_CONFIG_PATH)


def load_vertical_config(slug: str) -> VerticalConfig:
    path = VERTICALS_DIR / f"{slug}.yaml"
    raw = _load_yaml(path)
    return VerticalConfig.model_validate(raw)


def list_vertical_slugs() -> list[str]:
    return sorted(
        p.stem
        for p in VERTICALS_DIR.glob("*.yaml")
        if not p.name.startswith("_")
    )
