from __future__ import annotations

from typing import Any

from voice_generation_engine.schemas import (
    VoiceSpecification,
    VoiceTimeline,
    VoiceTimelineSegment,
)


def voice_spec_to_provider_request(
    spec: VoiceSpecification,
    *,
    provider_voice_id: str,
    pronounced_text: str | None = None,
) -> dict[str, Any]:
    text = pronounced_text if pronounced_text is not None else spec.text
    return {
        "text": text,
        "language": spec.language,
        "provider_voice_id": provider_voice_id,
        "delivery": spec.delivery.model_dump(),
        "target_duration_sec": spec.timing.target_duration_sec,
        "pauses": [p.model_dump() for p in spec.pauses],
        "emotion_curve": [e.model_dump() for e in spec.emotion_curve],
        "pronunciation": spec.pronunciation,
        "voice_type": spec.voice_type,
        "character_id": spec.character_id,
        "voice_profile_id": spec.voice_profile_id,
        "dialogue_id": spec.dialogue_id,
    }


def build_voice_timeline(
    *,
    specs_with_artifacts: list[dict[str, Any]],
    gap_sec: float = 0.4,
) -> VoiceTimeline:
    """
    Orchestrate multi-speaker takes into a VoiceTimeline.
    Each item: {spec: VoiceSpecification|dict, artifact_id, duration_sec, request_id?}
    """
    segments: list[VoiceTimelineSegment] = []
    cursor = 0.0
    for item in specs_with_artifacts:
        spec = item.get("spec") or {}
        if hasattr(spec, "model_dump"):
            spec = spec.model_dump()
        start_hint = (spec.get("timing") or {}).get("start_sec")
        dur = float(item.get("duration_sec") or (spec.get("timing") or {}).get("target_duration_sec") or 1.5)
        if start_hint is not None:
            start = float(start_hint)
            if start < cursor:
                start = cursor
        else:
            start = cursor
        end = round(start + dur, 3)
        segments.append(
            VoiceTimelineSegment(
                speaker=str(spec.get("character_slug") or spec.get("lineage", {}).get("speaker") or "speaker"),
                artifact_id=item.get("artifact_id"),
                start=round(start, 3),
                end=end,
                character_id=spec.get("character_id"),
                voice_profile_id=spec.get("voice_profile_id"),
                dialogue_id=spec.get("dialogue_id"),
                request_id=item.get("request_id"),
            )
        )
        cursor = end + gap_sec
    duration = max((s.end for s in segments), default=0.0)
    return VoiceTimeline(duration_sec=round(duration, 3), segments=segments)
