from __future__ import annotations

import re

from prompt_engine.registry import get_adapter
from prompt_engine.schemas import (
    CanonicalGenerationSpec,
    PromptConflict,
    PromptCriticResult,
    PromptPackageDoc,
    PromptQuality,
    PromptValidationResult,
)


_FAST_MOTION = re.compile(r"\b(run|running|sprint|dash|fast)\b", re.I)
_SLOW_ACTION = re.compile(r"\b(walks? slowly|slow walk|creep)\b", re.I)


def detect_conflicts(
    spec: CanonicalGenerationSpec, package: PromptPackageDoc
) -> list[PromptConflict]:
    conflicts: list[PromptConflict] = []
    action = (spec.subject.action or "").lower()
    prompt = package.positive_prompt.lower()

    if _SLOW_ACTION.search(action) and _FAST_MOTION.search(prompt) and "slowly" not in prompt:
        conflicts.append(
            PromptConflict(
                type="motion_conflict",
                severity="high",
                sources=["storyboard", "provider_prompt"],
                detail="Storyboard implies slow movement but prompt suggests fast motion.",
            )
        )

    if spec.constraints.get("preserve_character_identity") and "identity" not in prompt and "character reference" not in prompt and "facial identity" not in prompt:
        # soft — adapters usually inject component text
        if "maintain the exact facial identity" not in prompt:
            conflicts.append(
                PromptConflict(
                    type="identity_instruction_missing",
                    severity="medium",
                    sources=["constraints", "provider_prompt"],
                    detail="Character identity preservation requested but weakly represented.",
                )
            )

    cam = spec.camera.movement
    if cam and cam != "static" and cam.replace("_", " ") not in prompt and cam not in prompt:
        conflicts.append(
            PromptConflict(
                type="camera_underspecified",
                severity="low",
                sources=["storyboard", "provider_prompt"],
                detail=f"Camera movement '{cam}' not clearly reflected in prompt.",
            )
        )
    return conflicts


def validate_prompt(
    spec: CanonicalGenerationSpec, package: PromptPackageDoc, *, provider: str
) -> PromptValidationResult:
    adapter = get_adapter(provider)
    base = adapter.validate(spec, package)
    conflicts = detect_conflicts(spec, package)
    creative: list[str] = []
    safety: list[str] = []
    continuity: list[str] = []

    if not spec.objective:
        creative.append("missing objective")
    if spec.modality in {"video", "image"} and not (spec.subject.action or spec.objective):
        creative.append("missing action/objective")
    if spec.constraints.get("preserve_character_identity") and not spec.subject.character_id and not spec.subject.name:
        creative.append("character identity requested but no character bound")

    # Safety: refuse inventing weapons/gore keywords if canon forbids — lightweight
    banned = {"nsfw", "gore-porn"}
    blob = package.positive_prompt.lower()
    for b in banned:
        if b in blob:
            safety.append(f"unsafe token: {b}")

    if spec.continuity.get("character_state") is None and spec.modality == "video":
        continuity.append("character_state absent (soft)")

    high_conflicts = [c for c in conflicts if c.severity == "high"]
    ok = (
        base.ok
        and not base.structural
        and not safety
        and not high_conflicts
        and "missing objective" not in creative
    )
    return PromptValidationResult(
        ok=ok,
        structural=base.structural,
        creative=creative,
        safety=safety,
        continuity=continuity,
        conflicts=conflicts,
    )


def score_quality(
    spec: CanonicalGenerationSpec,
    package: PromptPackageDoc,
    validation: PromptValidationResult,
) -> PromptQuality:
    fields = [
        bool(spec.objective),
        bool(spec.subject.action or spec.modality in {"music", "voice"}),
        bool(spec.environment.location_name or spec.modality in {"music", "voice"}),
        bool(spec.camera.shot_type) if spec.modality in {"video", "image", "thumbnail"} else True,
        bool(package.positive_prompt),
    ]
    completeness = sum(1 for f in fields if f) / len(fields)

    consistency = 1.0 - 0.15 * len([c for c in validation.conflicts if c.severity == "high"])
    consistency -= 0.08 * len([c for c in validation.conflicts if c.severity == "medium"])
    consistency = max(0.0, min(1.0, consistency))

    provider_compat = 1.0 if validation.ok and not validation.structural else 0.6
    if validation.structural:
        provider_compat = max(0.0, 1.0 - 0.25 * len(validation.structural))

    asset_coverage = 0.5
    if spec.references:
        asset_coverage = min(1.0, 0.55 + 0.15 * len(spec.references))
    if spec.subject.character_id:
        asset_coverage = min(1.0, asset_coverage + 0.15)

    # Ambiguity: shorter clear prompts preferred; vague words hurt
    vague = len(re.findall(r"\b(somehow|maybe|various|things|stuff)\b", package.positive_prompt, re.I))
    ambiguity = min(1.0, 0.05 * vague + max(0, len(package.positive_prompt) - 900) / 2000)

    overall = (
        0.25 * completeness
        + 0.25 * consistency
        + 0.2 * provider_compat
        + 0.2 * asset_coverage
        + 0.1 * (1.0 - ambiguity)
    )
    return PromptQuality(
        completeness=round(completeness, 4),
        consistency=round(consistency, 4),
        provider_compatibility=round(provider_compat, 4),
        asset_coverage=round(asset_coverage, 4),
        ambiguity=round(ambiguity, 4),
        overall=round(overall, 4),
    )


def critique_prompt(
    spec: CanonicalGenerationSpec,
    package: PromptPackageDoc,
    validation: PromptValidationResult,
) -> PromptCriticResult:
    notes: list[str] = []
    fixes: list[str] = []

    faithful = bool(spec.subject.action and spec.subject.action.lower() in package.positive_prompt.lower()) or (
        spec.objective.split()[0].lower() in package.positive_prompt.lower() if spec.objective else False
    )
    if not faithful:
        # looser: objective words overlap
        words = set(w.lower() for w in (spec.subject.action or spec.objective or "").split() if len(w) > 3)
        prompt_words = set(package.positive_prompt.lower().split())
        faithful = len(words & prompt_words) >= max(1, len(words) // 3)

    preserves = "facial identity" in package.positive_prompt.lower() or bool(package.reference_assets)
    no_contradictions = not any(c.severity == "high" for c in validation.conflicts)
    priorities_clear = "objective:" in package.positive_prompt.lower() or bool(spec.objective)
    camera_clear = spec.modality not in {"video", "image"} or (
        spec.camera.shot_type.replace("_", " ") in package.positive_prompt.lower()
        or spec.camera.movement.replace("_", " ") in package.positive_prompt.lower()
    )
    env_ok = spec.modality in {"voice", "music"} or bool(spec.environment.location_name)
    refs_used = bool(package.reference_assets) or spec.modality in {"voice", "music"}
    not_verbose = len(package.positive_prompt) < 1200
    provider_ok = validation.ok or not validation.structural

    if not preserves and spec.constraints.get("preserve_character_identity"):
        fixes.append("Inject character identity component / references.")
    if not no_contradictions:
        fixes.append("Resolve high-severity conflicts before generation.")
    if not camera_clear:
        fixes.append("Restate camera shot/movement explicitly.")
    if not not_verbose:
        notes.append("Prompt is lengthy; consider trimming.")

    flags = [
        faithful,
        preserves,
        no_contradictions,
        priorities_clear,
        camera_clear,
        env_ok,
        refs_used,
        not_verbose,
        provider_ok,
    ]
    return PromptCriticResult(
        faithful_to_storyboard=faithful,
        preserves_character=preserves,
        no_contradictions=no_contradictions,
        visual_priorities_clear=priorities_clear,
        camera_unambiguous=camera_clear,
        environment_specified=env_ok,
        references_used=refs_used,
        not_verbose=not_verbose,
        provider_compatible=provider_ok,
        notes=notes,
        suggested_fixes=fixes,
        critic_score=round(sum(1 for f in flags if f) / len(flags), 4),
    )


def enrich_package(
    spec: CanonicalGenerationSpec, package: PromptPackageDoc, *, provider: str
) -> PromptPackageDoc:
    validation = validate_prompt(spec, package, provider=provider)
    quality = score_quality(spec, package, validation)
    critic = critique_prompt(spec, package, validation)
    package.validation = validation
    package.quality = quality
    package.critic = critic
    return package
