from __future__ import annotations

from trend_engine.v2.characters import adapt_to_characters
from trend_engine.v2.features.extractor import _extract_emotion, _extract_hook, _extract_story


def test_hook_detects_pov_fear() -> None:
    hook = _extract_hook("POV: I should never have opened that door in the haunted school")
    assert hook["hook_type"] in {"fear", "shock", "open_loop", "curiosity"}
    assert hook["open_loop"] or hook["first_person"]


def test_story_detects_pov() -> None:
    story = _extract_story("POV I accidentally entered the wrong classroom")
    assert story["pattern"] == "pov"
    assert story["cold_open"] is True


def test_emotion_fear_vs_joy() -> None:
    fear = _extract_emotion("Scary ghost horror story", {})
    joy = _extract_emotion("Happy kids colors rhyme song", {})
    assert fear["dominant"] == "fear"
    assert joy["dominant"] == "joy"


def test_character_adaptation_unique_hooks() -> None:
    opp = {
        "trend": "POV Horror",
        "hook": "I should never have opened that door...",
        "emotion": "fear",
        "story_pattern": "pov",
        "audio": "low_bass_narration",
        "target_audience": "16-24",
    }
    chars = [
        {"slug": "ghost_kid", "name": "Ghost Kid", "voice": "whisper", "traits": ["lonely"]},
        {"slug": "zombie_teacher", "name": "Zombie Teacher", "voice": "deadpan", "traits": ["ironic"]},
    ]
    adapted = adapt_to_characters(opp, chars, limit=2)
    assert len(adapted) == 2
    assert adapted[0]["character_name"] != adapted[1]["character_name"]
    assert "Ghost Kid" in adapted[0]["opening_line"]
