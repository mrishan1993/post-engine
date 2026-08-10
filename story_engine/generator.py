from __future__ import annotations

import hashlib
from typing import Any

from story_engine.schemas import (
    BeatBlueprint,
    DurationMeta,
    ForeshadowClue,
    HookBlueprint,
    OpenLoop,
    StoryBlueprint,
    StoryRequest,
    TensionPoint,
)
from story_engine.templates import CTA_BY_OBJECTIVE, HOOK_LIBRARY, TEMPLATES


def choose_template(request: StoryRequest) -> str:
    if request.creative_direction.template:
        return request.creative_direction.template
    fmt = (request.creative_direction.format or "").lower()
    emotion = (request.content_opportunity.emotion or "").lower()
    topic = (request.content_opportunity.topic or "").lower()
    if "loop" in topic or request.prediction.predicted_retention < 0.55:
        return "story_loop"
    if "pov" in fmt or "pov" in topic:
        return "pov"
    if emotion in {"fear", "curiosity"} or "horror" in topic or "mystery" in topic:
        return "mystery_reveal"
    if emotion in {"joy", "hope"}:
        return "problem_solution"
    return "three_act_short"


def allocate_durations(target: int, weights: dict[str, float], beats: list[str]) -> dict[str, float]:
    active = {b: weights[b] for b in beats if b in weights}
    total_w = sum(active.values()) or 1.0
    raw = {b: target * (w / total_w) for b, w in active.items()}
    # Round to 1 decimal, fix drift on escalation/ending
    rounded = {b: round(v, 1) for b, v in raw.items()}
    drift = round(target - sum(rounded.values()), 1)
    key = "escalation" if "escalation" in rounded else next(iter(rounded))
    rounded[key] = round(rounded[key] + drift, 1)
    return rounded


def build_blueprint(
    request: StoryRequest,
    *,
    character_context: dict[str, Any] | None = None,
    variant: int = 0,
    pattern: dict[str, Any] | None = None,
) -> StoryBlueprint:
    """Deterministic structured story architecture (Phase-2 generator; LLM-swappable later)."""
    template_name = choose_template(request)
    template = TEMPLATES[template_name]
    beats = list(template["beats"])
    if pattern and pattern.get("structure", {}).get("omit_twist"):
        beats = [b for b in beats if b != "twist"]

    target = int(request.creative_direction.target_duration_sec or 30)
    durs = allocate_durations(target, template["duration_weights"], beats)

    char = character_context or {}
    char_name = char.get("name") or "the protagonist"
    traits = (char.get("personality") or {}).get("traits") or char.get("traits") or []
    canon = char.get("canon") or {}
    forbidden = [str(x).lower() for x in (canon.get("forbidden") or [])]
    behavioral = char.get("behavioral_rules") or []

    topic = request.content_opportunity.topic
    emotion = request.content_opportunity.emotion
    platform = request.content_opportunity.platform

    seed = f"{topic}:{char_name}:{variant}:{template_name}"
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)

    hook_types = list(HOOK_LIBRARY.keys())
    # Bias hook by emotion / retention need
    if emotion == "fear":
        preferred = ["warning", "pov", "shock", "mystery"]
    elif emotion == "joy":
        preferred = ["challenge", "unexpected_discovery", "question"]
    else:
        preferred = ["curiosity_gap", "question", "mystery", "pov"]
    if request.prediction.predicted_retention and request.prediction.predicted_retention < 0.6:
        preferred = ["countdown", "shock", "warning"] + preferred
    hook_type = preferred[h % len(preferred)]
    if hook_type not in HOOK_LIBRARY:
        hook_type = hook_types[h % len(hook_types)]

    setting = _setting_for(topic, emotion, variant)
    conflict_type = _conflict_type(emotion, topic)
    stakes = _stakes(emotion, topic, forbidden)
    ending_type = _ending_type(template_name, variant, request)

    # Canon guard: strip violent actions if forbidden
    violence_blocked = any("harm" in f or "violent" in f or "species" in f for f in forbidden)
    if any("never intentionally harms" in str(b).lower() for b in behavioral):
        violence_blocked = True

    hook_event = f"{char_name} hears something impossible at {setting}."
    hook_text = _hook_text(hook_type, char_name, setting, topic, variant)
    setup_events = [
        f"{char_name} arrives at {setting}",
        f"notices a detail that shouldn't be there",
    ]
    conflict_event = f"A threat appears: {_threat(emotion, setting, violence_blocked)}"
    escalation_events = _escalation_events(char_name, setting, emotion, violence_blocked, variant)
    twist_event = _twist_event(char_name, setting, emotion, variant) if "twist" in beats else None
    ending_event = _ending_event(char_name, setting, ending_type, twist_event, variant)
    cta_objective = "comments" if emotion in {"fear", "curiosity"} else "follow"
    cta_text = CTA_BY_OBJECTIVE[cta_objective]

    open_loops = [
        OpenLoop(question=f"What is happening at {setting}?", status="escalated"),
        OpenLoop(question=f"Why does it involve {char_name}?", status="open"),
        OpenLoop(
            question="What is the source of the voice/signal?",
            status="resolved" if twist_event else "intentionally_open",
        ),
    ]
    if twist_event:
        open_loops.append(OpenLoop(question="How did they know the future/past?", status="intentionally_open"))

    foreshadowing: list[ForeshadowClue] = []
    if twist_event:
        foreshadowing = [
            ForeshadowClue(scene=1, clue="A detail appears that only makes sense after the reveal."),
            ForeshadowClue(scene=2, clue="A familiar phrase is used before the source is shown."),
        ]

    tension = _tension_curve(target, emotion, request.creative_direction.pacing)
    words = max(40, int(target * 2.4))
    density = round(len(escalation_events) + 4 / max(target, 1), 3)

    # Retention-focused tweak: stronger early hook intensity already in curve
    title = _title(topic, setting, variant)
    logline = f"{char_name} faces {_threat(emotion, setting, violence_blocked)} at {setting}."

    roles = []
    for c in request.characters:
        roles.append(
            {
                "character_id": c.character_id,
                "character_slug": c.character_slug or char.get("slug"),
                "role": c.role,
                "name": char_name if c.role == "protagonist" else None,
            }
        )
    if not roles:
        roles = [{"character_slug": char.get("slug"), "role": "protagonist", "name": char_name}]

    bp = StoryBlueprint(
        title=title,
        logline=logline,
        format={
            "type": request.creative_direction.format,
            "duration_sec": target,
            "platform": platform,
            "visual_style": request.creative_direction.visual_style,
            "pacing": request.creative_direction.pacing,
        },
        template=template_name,
        hook=HookBlueprint(
            type=hook_type,
            duration_sec=durs.get("hook", 3),
            objective="Create immediate curiosity / retention",
            event=hook_event,
            hook_text=hook_text,
            visual=f"Tight shot on {char_name} at {setting}",
            emotion=emotion,
        ),
        setup=BeatBlueprint(
            duration_sec=durs.get("setup", 4),
            objective="Establish context",
            events=setup_events,
        ),
        conflict=BeatBlueprint(
            duration_sec=durs.get("conflict", 5),
            objective="Introduce threat",
            event=conflict_event,
        ),
        escalation=BeatBlueprint(
            duration_sec=durs.get("escalation", 10),
            objective="Increase tension",
            events=escalation_events,
        ),
        twist=(
            BeatBlueprint(
                duration_sec=durs.get("twist", 5),
                objective="Recontextualize prior information",
                event=twist_event,
            )
            if twist_event
            else None
        ),
        ending=BeatBlueprint(
            duration_sec=durs.get("ending", 2),
            objective="Pay off setup",
            event=ending_event,
        ),
        cta=BeatBlueprint(
            duration_sec=durs.get("cta", 1),
            objective=cta_objective,
            text=cta_text,
            event=cta_text,
        ),
        conflict_meta={
            "type": conflict_type,
            "threat": _threat(emotion, setting, violence_blocked),
            "objective": f"Survive / understand {setting}",
            "obstacle": "Unknown source of the anomaly",
        },
        stakes=stakes,
        open_loops=open_loops,
        foreshadowing=foreshadowing,
        tension_curve=tension,
        loop={
            "enabled": bool(template.get("loop") or ending_type == "loop"),
            "type": "narrative_loop",
            "loop_point": 0,
        },
        duration=DurationMeta(
            target_seconds=target,
            estimated_seconds=float(target),
            narration_words=words,
            scene_count=len(beats),
        ),
        density=density,
        ending_type=ending_type,
        character_roles=roles,
    )
    return bp


def _setting_for(topic: str, emotion: str, variant: int) -> str:
    topic_l = topic.lower()
    if "school" in topic_l or emotion == "fear":
        options = ["Door 13", "the abandoned classroom", "the locked basement", "the empty hallway"]
    elif "color" in topic_l or emotion == "joy":
        options = ["the color classroom", "the rhyme playground", "the music corner"]
    else:
        options = ["the forgotten room", "the midnight street", "the quiet temple steps"]
    return options[variant % len(options)]


def _conflict_type(emotion: str, topic: str) -> str:
    if emotion == "fear" or "horror" in topic.lower():
        return "Person vs Supernatural"
    if emotion == "joy":
        return "Person vs Self"
    return "Person vs Unknown"


def _stakes(emotion: str, topic: str, forbidden: list[str]) -> list[str]:
    if emotion == "fear":
        stakes = ["Safety", "Identity", "Secret"]
    elif emotion == "joy":
        stakes = ["Opportunity", "Relationship"]
    else:
        stakes = ["Reputation", "Time", "Opportunity"]
    if any("harm" in f for f in forbidden):
        stakes = [s for s in stakes if s != "Life"]
    return stakes


def _ending_type(template: str, variant: int, request: StoryRequest) -> str:
    if template == "story_loop":
        return "loop"
    options = ["twist", "question", "cliffhanger", "part_2_setup", "reveal"]
    if request.content_opportunity.emotion == "joy":
        options = ["emotional_payoff", "resolution", "question"]
    return options[variant % len(options)]


def _hook_text(hook_type: str, char_name: str, setting: str, topic: str, variant: int) -> str:
    base = {
        "warning": f"If you hear your own voice at {setting}, don't answer.",
        "pov": f"POV: {char_name} walks into {setting} and it already knows their name.",
        "shock": f"{setting.capitalize()} was empty — until something whispered.",
        "question": f"What would you do if {setting} called you by name?",
        "curiosity_gap": f"Never open {setting} until you know who's inside.",
        "confession": f"I wasn't supposed to enter {setting}. I did anyway.",
        "countdown": f"You have 30 seconds before {setting} changes forever.",
        "mystery": f"Someone left a note about {setting} in my handwriting.",
        "challenge": f"Don't look away before {setting} opens.",
        "unexpected_discovery": f"I found a video of myself entering {setting} — from tomorrow.",
    }
    return base.get(hook_type, HOOK_LIBRARY.get(hook_type, f"Something is wrong at {setting}."))


def _threat(emotion: str, setting: str, violence_blocked: bool) -> str:
    if violence_blocked or emotion != "fear":
        return f"an impossible voice coming from {setting}"
    return f"an unknown presence behind {setting}"


def _escalation_events(
    char_name: str, setting: str, emotion: str, violence_blocked: bool, variant: int
) -> list[str]:
    if emotion == "fear":
        return [
            f"The voice begs {char_name} to come closer",
            "Lights begin flickering",
            f"{setting} starts changing on its own",
            "A familiar detail appears that shouldn't exist",
        ]
    if emotion == "joy":
        return [
            f"{char_name} tries a playful challenge",
            "A surprise helper shows up",
            "The puzzle gets harder in a fun way",
            "A big reveal sets up the ending cheer",
        ]
    return [
        f"{char_name} finds a second clue",
        "The anomaly spreads",
        "Time pressure increases",
        "A choice becomes unavoidable",
    ]


def _twist_event(char_name: str, setting: str, emotion: str, variant: int) -> str:
    twists = [
        f"The voice is coming from {char_name}'s own phone.",
        f"{setting} shows a recording from tomorrow.",
        f"The figure in the dark is {char_name}'s reflection — wrong.",
        f"A message reveals {char_name} left the clue earlier.",
    ]
    return twists[variant % len(twists)]


def _ending_event(
    char_name: str, setting: str, ending_type: str, twist: str | None, variant: int
) -> str:
    if ending_type == "loop":
        return f"As {setting} opens, the opening warning plays again — loop."
    if ending_type == "cliffhanger" or ending_type == "part_2_setup":
        return f"The screen cuts as {char_name} steps through — 'Part 2'."
    if ending_type == "question":
        return f"{char_name} stares at the proof. Freeze. Question hangs."
    if twist:
        return f"Payoff: {twist} The date on screen is tomorrow."
    return f"{char_name} escapes {setting}, changed."


def _tension_curve(target: int, emotion: str, pacing: str) -> list[TensionPoint]:
    start = 0.75 if emotion == "fear" else 0.55
    mid_dip = 0.4 if pacing != "fast" else 0.5
    peak = 0.98 if emotion == "fear" else 0.85
    return [
        TensionPoint(time=0, intensity=start),
        TensionPoint(time=round(target * 0.15, 1), intensity=mid_dip),
        TensionPoint(time=round(target * 0.4, 1), intensity=0.65),
        TensionPoint(time=round(target * 0.7, 1), intensity=0.85),
        TensionPoint(time=round(target * 0.88, 1), intensity=peak),
        TensionPoint(time=float(target - 1), intensity=0.55),
    ]


def _title(topic: str, setting: str, variant: int) -> str:
    if "door" in setting.lower():
        return ["Don't Open Door 13", "Door 13 Knows You", "Behind Door 13"][variant % 3]
    return f"{topic.title()} — {setting.title()}"
