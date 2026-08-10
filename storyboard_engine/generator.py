from __future__ import annotations

from typing import Any
from uuid import uuid4

from story_engine.schemas import StoryBlueprint
from storyboard_engine.camera import BEAT_SHOT_RECIPES, words_to_seconds
from storyboard_engine.continuity import ContinuityTracker
from storyboard_engine.platforms import get_platform
from storyboard_engine.schemas import (
    AssetRequirements,
    AudioBlock,
    CameraSpec,
    CaptionPlan,
    CompositionSpec,
    GenerationReq,
    GlobalDirection,
    LightingSpec,
    PacingMeta,
    PatternInterrupt,
    SceneSpec,
    ShotSpec,
    StoryboardDocument,
    StoryboardRequest,
    TransitionSpec,
)
from storyboard_engine.templates import STORYBOARD_TEMPLATES, choose_template


BEAT_ORDER = ["hook", "setup", "conflict", "escalation", "twist", "ending", "cta"]


def _beat_payloads(bp: StoryBlueprint) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    mapping = [
        ("hook", bp.hook),
        ("setup", bp.setup),
        ("conflict", bp.conflict),
        ("escalation", bp.escalation),
        ("twist", bp.twist),
        ("ending", bp.ending),
        ("cta", bp.cta),
    ]
    for name, beat in mapping:
        if beat is None:
            continue
        data = beat.model_dump() if hasattr(beat, "model_dump") else dict(beat)
        out.append((name, data))
    return out


def _emotion_at(tension_curve: list[Any], t: float, fallback: str) -> tuple[str, float]:
    if not tension_curve:
        return fallback, 0.5
    points = [(float(p.time), float(p.intensity)) for p in tension_curve]
    points.sort()
    intensity = points[0][1]
    for i, (pt, val) in enumerate(points):
        if t >= pt:
            intensity = val
        else:
            break
    if intensity < 0.45:
        label = "curiosity" if fallback != "fear" else "unease"
    elif intensity < 0.65:
        label = "unease"
    elif intensity < 0.8:
        label = "fear"
    elif intensity < 0.92:
        label = "panic"
    else:
        label = "shock"
    return label, intensity


def _char_name(bp: StoryBlueprint, character_context: dict[str, Any] | None) -> str:
    if character_context and character_context.get("name"):
        return str(character_context["name"])
    for role in bp.character_roles:
        if role.get("name"):
            return str(role["name"])
    return "the protagonist"


def _infer_location(bp: StoryBlueprint, request: StoryboardRequest) -> str:
    if request.location_query:
        return request.location_query
    logline = (bp.logline or "").lower()
    for token in ("school", "classroom", "hallway", "forest", "home", "street"):
        if token in logline:
            return f"Abandoned {token.title()}" if token in {"school", "hallway"} else token.title()
    return "Primary Location"


def _split_actions(beat: dict[str, Any], char: str, function: str) -> list[str]:
    events = list(beat.get("events") or [])
    if beat.get("event"):
        events = [beat["event"], *events]
    if beat.get("hook_text") and function == "hook":
        events = events or [beat.get("event") or f"{char} faces the hook moment."]
    if not events:
        events = [f"{char} continues the {function} beat."]
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for e in events:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _allocate_shot_durations(scene_dur: float, n: int, early_boost: bool, is_hook: bool) -> list[float]:
    if n <= 0:
        return []
    if n == 1:
        return [round(scene_dur, 3)]
    weights = [1.0] * n
    if early_boost and is_hook:
        weights[0] = 0.85
        if n > 1:
            weights[1] = 1.15
    total_w = sum(weights)
    raw = [scene_dur * (w / total_w) for w in weights]
    rounded = [round(x, 3) for x in raw]
    drift = round(scene_dur - sum(rounded), 3)
    rounded[-1] = round(rounded[-1] + drift, 3)
    return rounded


def build_storyboard(
    blueprint: StoryBlueprint | dict[str, Any],
    request: StoryboardRequest,
    *,
    character_context: dict[str, Any] | None = None,
    resolved_assets: dict[str, Any] | None = None,
) -> StoryboardDocument:
    """Convert a Story Blueprint into a time-coded visual/audio storyboard."""
    bp = (
        blueprint
        if isinstance(blueprint, StoryBlueprint)
        else StoryBlueprint.model_validate(blueprint)
    )
    platform = get_platform(request.platform)
    template_name = choose_template(bp.model_dump(), request.template)
    tmpl = STORYBOARD_TEMPLATES[template_name]
    char = _char_name(bp, character_context)
    location_name = _infer_location(bp, request)
    resolved = resolved_assets or {}

    visual_style = (
        request.visual_style
        or (bp.format or {}).get("visual_style")
        or tmpl.get("visual_style")
        or "cinematic_horror"
    )
    aspect = request.aspect_ratio or platform["aspect_ratio"]
    target = float(
        request.target_duration_sec
        or (bp.format or {}).get("duration_sec")
        or bp.duration.target_seconds
        or 30
    )

    global_direction = GlobalDirection(
        visual_style=visual_style,
        visual_reference={"style_id": request.style_id} if request.style_id else {},
        aspect_ratio=aspect,
        resolution=platform["resolution"],
        frame_rate=30,
        pacing=str((bp.format or {}).get("pacing") or tmpl["pacing"]),
        color_direction={"palette": tmpl["color_palette"]},
        lighting={"style": tmpl["lighting"]},
        camera_language={"style": tmpl["camera_style"], "movement": "restrained"},
        typography={"style": "bold_minimal"},
        subtitle_style={"enabled": True},
        platform=platform,
        template=template_name,
    )

    tracker = ContinuityTracker()
    tracker.enter_location(location_name)
    tracker.set_character(char, location=location_name, emotion="curious", prop="flashlight")
    tracker.move_prop("flashlight", char, "hand")
    tracker.move_prop("phone", char, "pocket")

    beats = _beat_payloads(bp)
    # Scale beat durations to target if needed
    raw_total = sum(float(b.get("duration_sec") or 0) for _, b in beats) or target
    scale = target / raw_total

    scenes: list[SceneSpec] = []
    interrupts: list[PatternInterrupt] = []
    music_cues: list[dict[str, Any]] = []
    t = 0.0
    retention_risk = (request.predicted_retention or 0.7) < 0.6
    early_boost = bool(tmpl.get("early_motion_boost") or retention_risk)

    char_id = None
    if character_context and character_context.get("id"):
        char_id = character_context["id"]
    elif request.character_ids:
        char_id = request.character_ids[0]

    location_id = (resolved.get("location") or {}).get("id")

    for seq, (function, beat) in enumerate(beats, start=1):
        dur = round(float(beat.get("duration_sec") or 2) * scale, 3)
        dur = max(0.8, dur)
        start = round(t, 3)
        end = round(t + dur, 3)
        emo_start, ten_start = _emotion_at(bp.tension_curve, start, bp.hook.emotion or "curiosity")
        emo_end, ten_end = _emotion_at(bp.tension_curve, end, bp.hook.emotion or "curiosity")

        actions = _split_actions(beat, char, function)
        tracker.enter_location(location_name)
        tracker.set_character(char, location=location_name, emotion=emo_end)

        # Prop state transitions around twist / escalation
        if function == "escalation":
            tracker.move_prop("flashlight", char, "hand")
        if function == "twist":
            tracker.move_prop("phone", None, "ground")
            tracker.move_prop("phone", None, "screen_up")
        if function == "ending" and "phone" in tracker.props:
            tracker.props["phone"]["position"] = "ground"

        narration_text = None
        if function == "hook":
            narration_text = beat.get("hook_text") or beat.get("text")
        elif function == "cta":
            narration_text = beat.get("text") or beat.get("event")
        elif function in {"twist", "conflict"} and beat.get("event"):
            # Short VO line for emphasis when retention risk
            if retention_risk or function == "twist":
                narration_text = None  # prefer silence / diegetic for twist

        narr_dur = words_to_seconds(narration_text)
        if narration_text and narr_dur > dur + 0.4:
            # Expand scene slightly to fit speech rather than invalidate
            end = round(start + max(dur, narr_dur + 0.3), 3)
            dur = round(end - start, 3)

        recipes = list(BEAT_SHOT_RECIPES.get(function, BEAT_SHOT_RECIPES["setup"]))
        # Retention: more cuts in early hook
        if function == "hook" and (early_boost or retention_risk) and len(recipes) < 2:
            recipes = recipes + [
                {
                    "shot_type": "close_up",
                    "movement": "handheld",
                    "angle": "eye_level",
                    "pattern": "face_reveal",
                }
            ]
        n_shots = min(len(recipes), max(1, len(actions)))
        if function == "escalation":
            n_shots = min(len(recipes), max(2, len(actions)))
        shot_durs = _allocate_shot_durations(dur, n_shots, early_boost, function == "hook")

        shots: list[ShotSpec] = []
        cursor = start
        for i in range(n_shots):
            recipe = recipes[i % len(recipes)]
            s_dur = shot_durs[i]
            s_end = round(cursor + s_dur, 3)
            action = actions[min(i, len(actions) - 1)]
            screen_dir = "right" if i % 2 == 0 else "toward"
            if function == "conflict" and i == 0:
                tracker.update_screen_direction("right")
            elif function == "conflict" and i == 1:
                tracker.update_screen_direction("toward", looking_at="opposite")
            else:
                tracker.update_screen_direction(screen_dir)

            shot_audio = AudioBlock(
                music={
                    "state": "rising" if function in {"escalation", "conflict"} else "hold",
                    "intensity": round(min(0.95, ten_start + i * 0.08), 2),
                },
                ambience={"type": "location_ambience", "intensity": 0.3},
                sfx=[],
            )
            if function == "hook" and i == 0 and narration_text:
                shot_audio.narration = {
                    "text": narration_text,
                    "estimated_duration_sec": narr_dur,
                }
            if function == "twist" and i == 0:
                shot_audio.music = {"action": "stop", "intensity": 0.0}
                shot_audio.silence = {"duration_sec": 0.8}
                shot_audio.sfx = [
                    {"type": "impact_soft", "timing": 0.2, "intensity": 0.7, "purpose": "reveal"}
                ]
                interrupts.append(
                    PatternInterrupt(
                        time_sec=cursor,
                        type="audio_cut",
                        purpose="increase tension before reveal",
                    )
                )
            if function == "escalation" and i == 1:
                shot_audio.sfx.append(
                    {
                        "type": "door_creak",
                        "timing": 0.3,
                        "intensity": 0.85,
                        "purpose": "threat",
                    }
                )
                interrupts.append(
                    PatternInterrupt(
                        time_sec=cursor + 0.3,
                        type="object_moves",
                        purpose="pattern interrupt",
                    )
                )

            captions: list[CaptionPlan] = []
            if function == "hook" and i == 0 and narration_text:
                captions.append(
                    CaptionPlan(
                        text=narration_text[:80],
                        start_sec=cursor,
                        end_sec=min(s_end, cursor + max(1.2, narr_dur)),
                        emphasis="high",
                        position=platform["caption_position"]["preferred"],
                    )
                )
            text_overlay = None
            if function == "cta":
                text_overlay = {
                    "text": beat.get("text") or beat.get("event") or "What would you do?",
                    "start_sec": cursor,
                    "end_sec": s_end,
                    "purpose": "cta",
                }
            elif function == "twist" and i == 0:
                text_overlay = {
                    "text": "12:47 AM",
                    "start_sec": cursor,
                    "end_sec": min(s_end, cursor + 1.5),
                    "purpose": "timestamp",
                }

            refs = []
            if char_id:
                refs.append(char_id)
            if location_id:
                refs.append(location_id)

            shot = ShotSpec(
                id=f"shot_{uuid4().hex[:8]}",
                sequence=i + 1,
                start_time_sec=cursor,
                end_time_sec=s_end,
                duration_sec=s_dur,
                shot_type=recipe["shot_type"],
                camera=CameraSpec(
                    angle=recipe["angle"],
                    movement=recipe["movement"],
                    lens="35mm" if recipe["shot_type"] != "extreme_close_up" else "85mm",
                    screen_direction=tracker.screen_direction,  # type: ignore[arg-type]
                ),
                subject={"character_id": char_id, "name": char},
                action=action,
                expression={"emotion": emo_end},
                composition=CompositionSpec(
                    framing="center" if recipe["shot_type"] != "over_the_shoulder" else "rule_of_thirds",
                    subject_position="foreground",
                ),
                environment={
                    "location_id": location_id,
                    "location_name": location_name,
                    "state": tracker.location.get("environmental_state"),
                },
                lighting=LightingSpec(
                    direction="side",
                    intensity="low" if template_name in {"horror", "mystery"} else "medium",
                    style=tmpl["lighting"],
                ),
                visual_priority={
                    "primary": "character" if "close" in recipe["shot_type"] else "environment",
                    "secondary": "prop" if function in {"twist", "escalation"} else "door",
                },
                transition=TransitionSpec(**{"in": "cut", "out": "cut"}),
                audio=shot_audio,
                captions=captions,
                text_overlay=text_overlay,
                generation=GenerationReq(
                    modality="video",
                    generation_type={"text_to_video": False, "image_to_video": True},
                    reference_assets=refs,
                    duration_sec=s_dur,
                ),
                pattern_name=recipe.get("pattern"),
            )
            shots.append(shot)
            cursor = s_end

        music = {
            "action": "start" if seq == 1 else "continue",
            "intensity": round(ten_start, 2),
            "mood": tmpl["music_mood"],
        }
        if function == "twist":
            music = {"action": "drop", "intensity": 0.05, "mood": tmpl["music_mood"]}
            music_cues.append({"time": start, "action": "drop_music"})
        if function == "escalation":
            music_cues.append({"time": start, "action": "increase_intensity"})
        if function == "ending":
            music_cues.append({"time": start, "action": "impact"})

        scene = SceneSpec(
            id=f"scene_{uuid4().hex[:8]}",
            sequence=seq,
            start_time_sec=start,
            end_time_sec=end,
            duration_sec=dur,
            narrative_function=function,
            objective=beat.get("objective"),
            emotional_state={"start": emo_start, "end": emo_end},
            tension={"start": round(ten_start, 3), "end": round(ten_end, 3)},
            location_id=location_id,
            location_name=location_name,
            characters=[
                {
                    "character_id": char_id,
                    "version": (character_context or {}).get("version")
                    or (character_context or {}).get("current_version"),
                    "name": char,
                    "role": "protagonist",
                }
            ],
            actions=actions,
            dialogue=None,
            narration=(
                {"text": narration_text, "estimated_duration_sec": narr_dur}
                if narration_text
                else None
            ),
            text_overlay=shots[-1].text_overlay if shots and function == "cta" else None,
            music=music,
            sound_effects=[sfx for sh in shots for sfx in (sh.audio.sfx or [])],
            shots=shots,
            character_state=tracker.snapshot()["characters"],
            prop_state=tracker.snapshot()["props"],
        )
        scenes.append(scene)
        t = end

    # Pattern interrupt for black cut before CTA if ending exists
    for sc in scenes:
        if sc.narrative_function == "ending" and sc.shots:
            interrupts.append(
                PatternInterrupt(
                    time_sec=sc.end_time_sec,
                    type="cut_to_black",
                    purpose="land ending before CTA",
                )
            )
            break

    all_shots = [sh for sc in scenes for sh in sc.shots]
    avg_shot = (
        round(sum(sh.duration_sec for sh in all_shots) / len(all_shots), 3) if all_shots else 0.0
    )
    duration = round(scenes[-1].end_time_sec, 3) if scenes else target
    cuts_per_10 = round((len(all_shots) / max(duration, 1)) * 10, 2)
    motion = round(
        sum(1 for sh in all_shots if sh.camera.movement not in {"static"}) / max(len(all_shots), 1),
        2,
    )
    novelty = round(min(0.95, 0.55 + 0.05 * len({sh.shot_type for sh in all_shots})), 2)

    expressions = sorted({(sh.expression or {}).get("emotion") for sh in all_shots if sh.expression})
    props = sorted(tracker.props.keys())
    asset_reqs = AssetRequirements(
        characters=[c for c in [char_id] if c]
        or [str(r.get("character_slug")) for r in bp.character_roles if r.get("character_slug")],
        locations=[location_id] if location_id else [location_name],
        props=props,
        expressions=[e for e in expressions if e],
        environment_states=["dark", "flickering_lights"]
        if template_name in {"horror", "mystery"}
        else ["neutral"],
        styles=[request.style_id] if request.style_id else [visual_style],
    )

    return StoryboardDocument(
        title=bp.title,
        story_id=request.story_id,
        platform=request.platform,
        duration_sec=duration,
        global_direction=global_direction,
        scenes=scenes,
        pacing=PacingMeta(
            average_shot_duration_sec=avg_shot,
            cuts_per_10_sec=cuts_per_10,
            motion_density=motion,
            visual_novelty=novelty,
        ),
        pattern_interrupts=interrupts,
        asset_requirements=asset_reqs,
        resolved_assets=resolved,
        music_cues=music_cues,
    )
