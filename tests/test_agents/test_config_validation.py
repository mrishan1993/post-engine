from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.loader import load_vertical_config
from config.schema import SafetyQAConfig, VerticalConfig


def test_kids_rhymes_config_loads() -> None:
    cfg = load_vertical_config("kids_rhymes")
    assert cfg.slug == "kids_rhymes"
    assert cfg.safety_qa.human_review_required is True


def test_human_review_cannot_be_disabled() -> None:
    with pytest.raises(ValidationError):
        SafetyQAConfig(classifier_thresholds={"violence": 0.1}, human_review_required=False)


def test_vertical_requires_rig_path_for_fixed_rig() -> None:
    raw = load_vertical_config("kids_rhymes").model_dump()
    raw["visual_agent"]["rig_path"] = None
    with pytest.raises(ValidationError):
        VerticalConfig.model_validate(raw)
