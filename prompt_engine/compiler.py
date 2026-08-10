from __future__ import annotations

from typing import Any

from prompt_engine.components import select_components
from prompt_engine.registry import get_adapter, select_provider
from prompt_engine.schemas import (
    CanonicalCamera,
    CanonicalEnvironment,
    CanonicalGenerationSpec,
    CanonicalSubject,
    CompileRequest,
    Modality,
    PromptPackageDoc,
)


def shot_to_cgs(
    shot: dict[str, Any],
    *,
    scene: dict[str, Any] | None = None,
    global_direction: dict[str, Any] | None = None,
    modality: Modality = "video",
    character_context: dict[str, Any] | None = None,
    resolved_assets: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
) -> CanonicalGenerationSpec:
    """Deterministic Storyboard shot → Canonical Generation Spec."""
    scene = scene or {}
    gd = global_direction or {}
    char_ctx = character_context or {}
    resolved = resolved_assets or {}

    subject_raw = shot.get("subject") or {}
    env_raw = shot.get("environment") or {}
    camera_raw = shot.get("camera") or {}
    expression = shot.get("expression") or {}
    audio = shot.get("audio") or {}

    char_id = subject_raw.get("character_id") or char_ctx.get("id")
    char_name = subject_raw.get("name") or char_ctx.get("name")
    canon = (char_ctx.get("canonical_data") or {}) if char_ctx else {}
    identity = canon.get("identity") or {}
    personality = canon.get("personality") or {}
    traits = personality.get("traits") or char_ctx.get("traits") or []

    location = resolved.get("location") or {}
    location_id = env_raw.get("location_id") or scene.get("location_id") or location.get("id")
    location_name = (
        env_raw.get("location_name")
        or scene.get("location_name")
        or location.get("name")
        or "location"
    )

    refs: list[str] = []
    for r in (shot.get("generation") or {}).get("reference_assets") or []:
        if r and r not in refs:
            refs.append(str(r))
    if char_id and char_id not in refs:
        refs.insert(0, str(char_id))
    if location_id and str(location_id) not in refs:
        refs.append(str(location_id))
    style = resolved.get("style") or {}
    if style.get("id") and style["id"] not in refs:
        refs.append(style["id"])

    action = shot.get("action") or (scene.get("actions") or ["acts"])[0]
    emotion = expression.get("emotion") or (scene.get("emotional_state") or {}).get("end") or "tense"
    objective = scene.get("objective") or f"Show {char_name or 'subject'}: {action}"

    env_state = {
        "lighting": (shot.get("lighting") or {}).get("intensity") or "low",
        "atmosphere": "ominous" if "horror" in str(gd.get("visual_style") or "").lower() else "neutral",
        "environment_state": env_raw.get("state") or "default",
    }

    narration = None
    if audio.get("narration"):
        narration = audio["narration"]
    elif scene.get("narration"):
        narration = scene["narration"]

    music = None
    if modality == "music":
        music = scene.get("music") or gd.get("music") or {"mood": "ominous"}
    elif audio.get("music"):
        music = audio.get("music")

    sfx = list(audio.get("sfx") or scene.get("sound_effects") or [])

    continuity = {
        "scene_id": scene.get("id"),
        "narrative_function": scene.get("narrative_function"),
        "character_state": scene.get("character_state"),
        "prop_state": scene.get("prop_state"),
        "previous_scene": None,
    }

    return CanonicalGenerationSpec(
        modality=modality,
        objective=str(objective),
        duration_sec=float(shot.get("duration_sec") or scene.get("duration_sec") or 4),
        aspect_ratio=str(gd.get("aspect_ratio") or "9:16"),
        resolution=gd.get("resolution"),
        subject=CanonicalSubject(
            character_id=char_id,
            character_version=char_ctx.get("version") or char_ctx.get("current_version"),
            character_slug=char_ctx.get("slug"),
            name=char_name,
            action=action,
            emotion=emotion,
            immutable=identity,
            behavior=list(traits) if isinstance(traits, list) else [],
            visual_references=[r for r in refs if r == char_id] if char_id else [],
        ),
        environment=CanonicalEnvironment(
            location_id=location_id,
            location_name=location_name,
            state=env_state,
            references=[str(location_id)] if location_id else [],
        ),
        camera=CanonicalCamera(
            shot_type=str(shot.get("shot_type") or "medium"),
            angle=str(camera_raw.get("angle") or "eye_level"),
            movement=str(camera_raw.get("movement") or "static"),
            lens=camera_raw.get("lens"),
            screen_direction=camera_raw.get("screen_direction"),
        ),
        composition=dict(shot.get("composition") or {}),
        visual_style={
            "name": gd.get("visual_style"),
            "style_id": (gd.get("visual_reference") or {}).get("style_id") or style.get("id"),
            "palette": (gd.get("color_direction") or {}).get("palette"),
        },
        lighting=dict(shot.get("lighting") or gd.get("lighting") or {}),
        motion={
            "speed": "slow" if str(camera_raw.get("movement") or "").startswith("slow") else "medium",
            "intensity": "medium",
            "style": (gd.get("camera_language") or {}).get("style"),
        },
        audio={
            "ambience": (audio.get("ambience") or {}).get("type") if isinstance(audio.get("ambience"), dict) else audio.get("ambience"),
            "music": music,
            "silence": audio.get("silence"),
        },
        continuity=continuity,
        references=refs,
        constraints={
            "preserve_character_identity": True,
            "preserve_environment": True,
            "no_new_objects": True,
            "preserve_face": True,
            "preserve_age": True,
        },
        narration=narration if isinstance(narration, dict) else ({"text": narration} if narration else None),
        text_overlay=shot.get("text_overlay") or scene.get("text_overlay"),
        music=music if isinstance(music, dict) else None,
        sfx=sfx,
        image_purpose="thumbnail" if modality == "thumbnail" else "storyboard_frame",
        lineage=lineage or {},
    )


def compile_package(
    spec: CanonicalGenerationSpec,
    *,
    provider: str | None = None,
) -> tuple[str, PromptPackageDoc]:
    """CGS → provider PromptPackage via adapter."""
    needs = {
        "preserve_character_identity": bool(spec.constraints.get("preserve_character_identity")),
        "camera_motion": spec.camera.movement not in {"static", None},
        "duration_sec": spec.duration_sec,
    }
    chosen = select_provider(spec.modality, preferred=provider, **needs)
    adapter = get_adapter(chosen)
    components = select_components(spec)
    package = adapter.compile(spec, components=components)
    package.estimate = {
        "provider": chosen,
        "estimated_cost": adapter.estimate_cost(spec),
        "estimated_latency_sec": adapter.estimate_latency(spec),
        "confidence": 0.85,
    }
    return chosen, package


def compile_from_request(
    request: CompileRequest,
    *,
    shot: dict[str, Any],
    scene: dict[str, Any] | None = None,
    global_direction: dict[str, Any] | None = None,
    character_context: dict[str, Any] | None = None,
    resolved_assets: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
) -> tuple[CanonicalGenerationSpec, PromptPackageDoc, str]:
    spec = shot_to_cgs(
        shot,
        scene=scene,
        global_direction=global_direction,
        modality=request.modality,
        character_context=character_context,
        resolved_assets=resolved_assets,
        lineage=lineage,
    )
    provider, package = compile_package(spec, provider=request.provider)
    return spec, package, provider
