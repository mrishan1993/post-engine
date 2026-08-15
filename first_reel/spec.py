"""First Reel #1 — 2026 is the new 2016 nostalgia vertical slice.

Not another intelligence engine: composes existing engines end-to-end.
"""

from __future__ import annotations

from typing import Any


TREND_ID = "2026_is_the_new_2016"
HOOK = "POV: You find your 2016 phone"
PUNCHLINE = "bro was actually happier."
CAPTION = "2016 really had no business being this good 😭"
HASHTAGS = ["#2016", "#nostalgia", "#2016nostalgia"]

SHOTS: list[dict[str, Any]] = [
    {
        "shot": 1,
        "t0": 0.0,
        "t1": 1.5,
        "label": "HOOK",
        "visual": "Close-up modern phone, slightly imperfect phone-cam",
        "text": HOOK,
        "narrative": "hook",
    },
    {
        "shot": 2,
        "t0": 1.5,
        "t1": 3.0,
        "label": "UNLOCK",
        "visual": "Phone unlock → date 2016, old UI aesthetic",
        "text": "2016",
        "narrative": "setup",
    },
    {
        "shot": 3,
        "t0": 3.0,
        "t1": 5.0,
        "label": "SELFIE",
        "visual": "Flash selfie, grain, 2016 colors",
        "text": "why did I dress like this 😭",
        "narrative": "escalation",
    },
    {
        "shot": 4,
        "t0": 5.0,
        "t1": 7.0,
        "label": "STATUS",
        "visual": "Old status/message bubble",
        "text": "Life is good ❤️",
        "narrative": "escalation",
    },
    {
        "shot": 5,
        "t0": 7.0,
        "t1": 9.5,
        "label": "MONTAGE",
        "visual": "Music player, Snapchat filter, wired earphones, old IG UI",
        "text": None,
        "narrative": "reveal",
    },
    {
        "shot": 6,
        "t0": 9.5,
        "t1": 12.0,
        "label": "PUNCHLINE",
        "visual": "Black / sparse frame",
        "text": PUNCHLINE,
        "narrative": "payoff",
    },
    {
        "shot": 7,
        "t0": 12.0,
        "t1": 13.0,
        "label": "LOOP",
        "visual": "Return to phone unlock (loop)",
        "text": HOOK,
        "narrative": "loop",
    },
]


def reel_spec() -> dict[str, Any]:
    return {
        "name": "first_reel_2016_phone",
        "format": "9:16",
        "width": 1080,
        "height": 1920,
        "duration_sec": 13.0,
        "duration_range": "10-14s",
        "platform": "instagram",
        "trend": {
            "trend_id": TREND_ID,
            "category": "nostalgia",
            "platform": "instagram",
            "velocity": "high",
            "freshness": "high",
            "velocity_score": 0.9,
            "freshness_score": 0.88,
            "saturation_score": 0.22,
            "opportunity_score": 0.9,
            "expiration_estimate": "short",
            "source_confidence": 0.86,
            "viral_mechanism": "nostalgia_reveal",
            "title": "2026 is the new 2016 nostalgia wave",
        },
        "opportunity": {
            "type": "trend_adaptation",
            "concept": HOOK,
            "objective": "reach",
            "format": "reel",
            "duration": "10-14s",
            "hook": HOOK,
            "audience": "young adults / nostalgia audience",
            "priority": "P0",
        },
        "story": {
            "beginning": "Present-day person discovers old phone.",
            "escalation": "Increasingly embarrassing 2016 memories.",
            "payoff": "Memories feel happier than the present.",
            "loop": "Phone screen returns to opening state.",
        },
        "shots": SHOTS,
        "audio": {
            "audio_strategy": "platform_native",
            "trend_audio": True,
            "note": "Select current native Instagram trend audio at publish time",
        },
        "caption": CAPTION,
        "hashtags": HASHTAGS,
        "creative_direction": {
            "style": "phone-camera imperfect nostalgia",
            "avoid": [
                "cinematic corporate",
                "generic AI imagery",
                "logo intro",
                "heavy branding",
            ],
        },
    }


def creative_override() -> dict[str, Any]:
    spec = reel_spec()
    return {
        "objective": "reach",
        "creative": {
            "hook": HOOK,
            "story": (
                "POV find 2016 phone → unlock → selfie → status → montage → "
                f"punchline '{PUNCHLINE}' → loop"
            ),
            "emotional_arc": "curiosity → cringe → warmth → loop",
            "payoff": PUNCHLINE,
            "CTA": CAPTION,
            "angle": "nostalgia_phone_pov",
            "shots": SHOTS,
        },
        "visual": {
            "visual_style": "2016 phone-cam, flash, grain, Snapchat overlays",
            "aspect_ratio": "9:16",
            "shot_requirements": [s["label"] for s in SHOTS],
        },
        "audio": dict(spec["audio"]),
        "editing": {
            "duration": 13,
            "pacing": "fast_cuts",
            "transitions": "hard_cut",
            "caption_style": "bottom_safe_bold_nostalgia",
            "loop": True,
        },
        "qa_requirements": {
            "first_frame_hook": True,
            "hook_without_audio": True,
            "aspect_ratio": "9:16",
            "duration": True,
            "loop_works": True,
        },
        "publishing_requirements": {
            "platform": "instagram",
            "require_qa": True,
            "caption": CAPTION,
            "title": HOOK,
            "hashtags": HASHTAGS,
            "audio_strategy": "platform_native",
            "trend_audio": True,
        },
    }
