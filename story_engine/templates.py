from __future__ import annotations

from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "three_act_short": {
        "beats": ["hook", "setup", "conflict", "escalation", "twist", "ending", "cta"],
        "duration_weights": {
            "hook": 0.10,
            "setup": 0.13,
            "conflict": 0.17,
            "escalation": 0.33,
            "twist": 0.17,
            "ending": 0.07,
            "cta": 0.03,
        },
    },
    "pov": {
        "beats": ["hook", "setup", "conflict", "escalation", "twist", "ending", "cta"],
        "duration_weights": {
            "hook": 0.12,
            "setup": 0.12,
            "conflict": 0.16,
            "escalation": 0.30,
            "twist": 0.18,
            "ending": 0.08,
            "cta": 0.04,
        },
    },
    "mystery_reveal": {
        "beats": ["hook", "setup", "conflict", "escalation", "twist", "ending", "cta"],
        "duration_weights": {
            "hook": 0.10,
            "setup": 0.15,
            "conflict": 0.15,
            "escalation": 0.30,
            "twist": 0.20,
            "ending": 0.07,
            "cta": 0.03,
        },
    },
    "story_loop": {
        "beats": ["hook", "setup", "conflict", "escalation", "ending", "cta"],
        "duration_weights": {
            "hook": 0.12,
            "setup": 0.15,
            "conflict": 0.18,
            "escalation": 0.35,
            "ending": 0.15,
            "cta": 0.05,
        },
        "loop": True,
    },
    "problem_solution": {
        "beats": ["hook", "setup", "conflict", "escalation", "ending", "cta"],
        "duration_weights": {
            "hook": 0.10,
            "setup": 0.20,
            "conflict": 0.20,
            "escalation": 0.25,
            "ending": 0.20,
            "cta": 0.05,
        },
    },
}

HOOK_LIBRARY = {
    "curiosity_gap": "Never do X until you understand Y.",
    "warning": "If you hear your own voice behind a locked door, don't answer.",
    "pov": "POV: you walk into the wrong room and it already knows your name.",
    "question": "What would you do if your phone showed tomorrow?",
    "shock": "The classroom was empty — until something whispered my name.",
    "confession": "I wasn't supposed to open Door 13. I did anyway.",
    "countdown": "You have 30 seconds before the lights go out.",
    "mystery": "Someone left a note in my handwriting I never wrote.",
    "challenge": "Don't look away before the door opens.",
    "unexpected_discovery": "I found a video of myself from tomorrow.",
}

ENDING_TYPES = [
    "resolution",
    "twist",
    "cliffhanger",
    "emotional_payoff",
    "reveal",
    "question",
    "loop",
    "part_2_setup",
]

CTA_BY_OBJECTIVE = {
    "comments": "Would you have opened the door?",
    "follow": "Follow for part 2.",
    "share": "Send this to someone who'd open it.",
    "save": "Save this for later — you'll need it.",
    "watch_part_2": "Part 2 drops next. Don't miss it.",
    "choose": "Comment A or B — what do you choose?",
}
