from __future__ import annotations

from typing import Any

from db.models import PromptPackage
from music_sfx_engine.schemas import EnergyPoint, MusicMood, MusicSpecification


def music_spec_to_provider_request(
    spec: MusicSpecification,
    *,
    prompt: str | None = None,
    original_provider_prompt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mood = spec.mood.primary
    positive = prompt or (
        f"Instrumental {spec.genre} score, mood {mood}, tempo ~{spec.tempo_bpm} BPM, "
        f"instruments: {', '.join(spec.instrumentation)}. Duration {spec.duration_sec}s. "
        + ("No vocals." if not spec.vocals_enabled else "Vocals allowed.")
    )
    return {
        "prompt": positive,
        "genre": spec.genre,
        "mood": mood,
        "secondary_mood": spec.mood.secondary,
        "tempo_bpm": spec.tempo_bpm,
        "instrumentation": list(spec.instrumentation),
        "vocals_enabled": spec.vocals_enabled,
        "duration_sec": spec.duration_sec,
        "energy_curve": [e.model_dump() for e in spec.energy_curve],
        "segments": list(spec.segments),
        "purpose": spec.purpose,
        "character_theme": spec.character_theme,
        "world_theme": spec.world_theme,
        "original_provider_prompt": original_provider_prompt or {},
    }


def from_prompt_package(pkg: PromptPackage) -> MusicSpecification:
    doc = pkg.provider_prompt or {}
    params = doc.get("parameters") or {}
    energy_raw = params.get("energy_curve") or {}
    energy: list[EnergyPoint] = []
    if isinstance(energy_raw, dict):
        for k, v in energy_raw.items():
            try:
                energy.append(EnergyPoint(time=float(k), intensity=float(v)))
            except Exception:  # noqa: BLE001
                continue
    elif isinstance(energy_raw, list):
        for item in energy_raw:
            if isinstance(item, dict):
                energy.append(EnergyPoint.model_validate(item))
    return MusicSpecification(
        purpose="background_score",
        mood=MusicMood(primary=str(params.get("mood") or "ominous")),
        genre=str(params.get("genre") or "cinematic_horror"),
        tempo_bpm=float(params.get("tempo_bpm") or 82),
        instrumentation=list(params.get("instrumentation") or ["low_drone", "strings"]),
        vocals_enabled=bool(params.get("vocals") or False),
        energy_curve=energy,
        duration_sec=float(params.get("duration_sec") or 30),
    )
