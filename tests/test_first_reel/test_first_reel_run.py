from __future__ import annotations

from amp_platform.events import EventType, get_bus, reset_bus
from db.session import get_session
from first_reel.gates import check_audio_strategy, check_first_frame_hook, check_lineage, check_trend_freshness
from first_reel.runner import run_first_reel
from first_reel.spec import creative_override, reel_spec
from generation_engine.providers.registry import reset_providers


def test_first_reel_spec_and_gates() -> None:
    spec = reel_spec()
    assert spec["trend"]["trend_id"] == "2026_is_the_new_2016"
    assert spec["audio"]["audio_strategy"] == "platform_native"
    ok, _ = check_trend_freshness(spec["trend"])
    assert ok
    override = creative_override()
    hook_ok, issues = check_first_frame_hook(override["creative"])
    assert hook_ok, issues
    assert check_audio_strategy(override["audio"], {"audio_strategy": "platform_native"})


def test_stale_trend_gate() -> None:
    ok, reason = check_trend_freshness(
        {"freshness_score": 0.2, "trend_stage": "accelerating"},
        min_freshness=0.45,
    )
    assert not ok
    ok2, _ = check_trend_freshness({"freshness_score": 0.9, "trend_stage": "saturated"})
    assert not ok2


def test_first_reel_vertical_slice(db_url: str) -> None:
    reset_bus()
    reset_providers()
    with get_session(db_url) as session:
        result = run_first_reel(session, character_slug="ghost_kid", publish=True)
        assert result["ok"], result
        assert result["status"] in {"PUBLISHED", "MEASURING", "LEARNING"}
        lin = result["lineage"]
        for key in (
            "content_id",
            "trend_id",
            "strategy_id",
            "campaign_id",
            "publication_id",
        ):
            assert lin.get(key), f"missing {key}"
        # Hardened aliases
        assert lin.get("creative_id") or lin.get("concept_id")
        assert lin.get("qa_run_id") or lin.get("qa_id")
        assert lin.get("assembly_run_id") or lin.get("assembly_id")
        assert lin.get("generation_run_id") or lin.get("generation_request_ids")
        assert lin.get("render_uri")
        assert lin.get("audio_strategy") == "platform_native" or result["acceptance"]["AC8_platform_native_audio"]

        acc = result["acceptance"]
        assert acc["AC1_trend_detected"]
        assert acc["AC3_creative_brief"]
        assert acc["AC6_assembled"]
        assert acc["AC7_qa"]
        assert acc["AC9_published"]
        assert acc["AC10_publication_id"]
        assert acc["AC12_learning"]

        lineage_ok, missing = check_lineage(lin)
        assert lineage_ok, missing

        assert result["package"]
        assert result["package"]["package_path"]
        from pathlib import Path

        assert Path(result["package"]["package_path"]).exists()
        frames_dir = Path(result["package"]["frames_dir"])
        assert frames_dir.exists()
        assert list(frames_dir.glob("shot_*.png"))

        seen = {e.event_type for e in get_bus().history}
        assert EventType.ORCHESTRATION_JOB_CREATED in seen
        assert EventType.ORCHESTRATION_PUBLISHED in seen
        assert EventType.ORCHESTRATION_LEARNING_HANDOFF in seen
