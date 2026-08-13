from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from db.models import PronunciationEntry
from voice_generation_engine.schemas import (
    DeliverySpec,
    DialogueLine,
    DialogueScript,
    PauseSpec,
    TimingSpec,
    VoiceSpecification,
)
from voice_generation_engine.registry import resolve_character_voice


def extract_dialogue_from_storyboard(document: dict[str, Any]) -> DialogueScript:
    """Pull structured dialogue/narration from storyboard — do not invent lines."""
    lines: list[DialogueLine] = []
    for sc in document.get("scenes") or []:
        # Scene-level narration
        narr = sc.get("narration")
        if isinstance(narr, dict) and narr.get("text"):
            speaker = "narrator"
            chars = sc.get("characters") or []
            char_id = chars[0].get("character_id") if chars else None
            slug = (chars[0].get("name") or chars[0].get("slug") if chars else None) or speaker
            lines.append(
                DialogueLine(
                    speaker=str(slug).lower().replace(" ", "_") if char_id else "narrator",
                    line=str(narr["text"]),
                    character_id=char_id,
                    emotion=(sc.get("emotional_state") or {}).get("end"),
                    start_sec=float(sc.get("start_time_sec") or 0),
                    dialogue_id=f"dlg_{uuid4().hex[:8]}",
                )
            )
        for sh in sc.get("shots") or []:
            audio = sh.get("audio") or {}
            shot_start = float(sh.get("start_time_sec") or sc.get("start_time_sec") or 0)
            for key in ("narration", "dialogue"):
                block = audio.get(key)
                if isinstance(block, dict) and block.get("text"):
                    chars = sc.get("characters") or []
                    char_id = block.get("character_id") or (
                        chars[0].get("character_id") if chars else None
                    )
                    speaker = str(
                        block.get("speaker")
                        or (chars[0].get("name") if chars else "narrator")
                        or "narrator"
                    )
                    emo = block.get("emotion") or (sc.get("emotional_state") or {}).get("end")
                    lines.append(
                        DialogueLine(
                            speaker=speaker.lower().replace(" ", "_"),
                            line=str(block["text"]),
                            character_id=char_id,
                            emotion=emo,
                            intensity=float(block.get("intensity") or 0.7),
                            start_sec=shot_start,
                            dialogue_id=str(block.get("id") or f"dlg_{uuid4().hex[:8]}"),
                            storyboard_shot_id=sh.get("id"),
                        )
                    )
    return DialogueScript(lines=lines)


def build_voice_specs_from_dialogue(
    session: Session,
    dialogue: DialogueScript,
    *,
    default_language: str = "en-IN",
) -> list[VoiceSpecification]:
    specs: list[VoiceSpecification] = []
    for line in dialogue.lines:
        char, profile = resolve_character_voice(
            session,
            character_id=line.character_id,
            character_slug=line.speaker if not line.character_id else None,
        )
        emotion = line.emotion or "neutral"
        intensity = float(line.intensity if line.intensity is not None else 0.65)
        rate = 0.88 if emotion in {"fear", "fearful", "whisper", "sad"} else 1.0
        pauses = _infer_pauses(line.line, emotion)
        target = _estimate_duration(line.line, rate, pauses)
        specs.append(
            VoiceSpecification(
                character_id=char.id if char else line.character_id,
                character_slug=char.slug if char else line.speaker,
                voice_profile_id=profile.id if profile else line.voice_profile_id,
                language=default_language,
                voice_type="narrator" if line.speaker == "narrator" else "dialogue",
                script={"text": line.line},
                delivery=DeliverySpec(
                    emotion=emotion,
                    intensity=intensity,
                    energy=max(0.2, intensity - 0.15),
                    speaking_rate=rate,
                    pitch=-0.05 if emotion in {"fear", "whisper"} else 0.0,
                    volume=0.65 if emotion in {"whisper", "fear"} else 0.85,
                ),
                timing=TimingSpec(target_duration_sec=target, start_sec=line.start_sec),
                pauses=pauses,
                dialogue_id=line.dialogue_id,
                storyboard_shot_id=line.storyboard_shot_id,
                speech_profile=((char.canonical_data or {}).get("voice") or {}) if char else {},
                lineage={"speaker": line.speaker},
            )
        )
    return specs


def build_voice_spec_from_text(
    *,
    text: str,
    character_id: str | None = None,
    character_slug: str | None = None,
    voice_profile_id: str | None = None,
    emotion: str = "neutral",
    intensity: float = 0.6,
    language: str = "en-IN",
) -> VoiceSpecification:
    rate = 0.88 if emotion in {"fear", "fearful", "whisper"} else 1.0
    pauses = _infer_pauses(text, emotion)
    return VoiceSpecification(
        character_id=character_id,
        character_slug=character_slug,
        voice_profile_id=voice_profile_id,
        language=language,
        voice_type="dialogue",
        script={"text": text},
        delivery=DeliverySpec(
            emotion=emotion,
            intensity=intensity,
            energy=max(0.2, intensity - 0.1),
            speaking_rate=rate,
            pitch=-0.05 if emotion in {"fear", "whisper"} else 0.0,
            volume=0.65 if emotion == "whisper" else 0.85,
        ),
        timing=TimingSpec(target_duration_sec=_estimate_duration(text, rate, pauses)),
        pauses=pauses,
    )


def apply_pronunciations(
    session: Session, text: str, *, language: str = "en"
) -> tuple[str, dict[str, Any]]:
    """Apply pronunciation dictionary; returns (annotated_text, applied_map)."""
    from sqlalchemy import select

    rows = list(session.scalars(select(PronunciationEntry)).all())
    applied: dict[str, Any] = {}
    out = text
    for row in rows:
        if row.language not in {language, language.split("-")[0], "en"}:
            continue
        if row.term and row.term in out:
            replacement = row.pronunciation or row.phoneme or row.term
            out = out.replace(row.term, replacement)
            applied[row.term] = {"pronunciation": row.pronunciation, "phoneme": row.phoneme}
    return out, applied


def _infer_pauses(text: str, emotion: str) -> list[PauseSpec]:
    pauses: list[PauseSpec] = []
    # Dramatic pause after ellipsis / Wait
    if "..." in text or "…" in text:
        before = text.split("...")[0].split("…")[0].strip().split()
        if before:
            pauses.append(
                PauseSpec(after_word=before[-1].strip(".,!?\"'"), duration_ms=400, type="dramatic")
            )
    for marker in ("Wait", "wait", "Don't", "No"):
        if marker in text.split() or any(w.strip(".,!?\"'") == marker for w in text.split()):
            pauses.append(PauseSpec(after_word=marker.strip(".,!?\"'"), duration_ms=300, type="dramatic"))
            break
    if emotion in {"fear", "fearful", "panic"} and "door" in text.lower():
        pauses.append(PauseSpec(after_word="open", duration_ms=300, type="dramatic"))
    return pauses


def _estimate_duration(text: str, rate: float, pauses: list[PauseSpec]) -> float:
    words = [w for w in re.findall(r"\S+", text) if w]
    # ~2.5 words/sec at rate 1.0
    base = len(words) / (2.5 * max(rate, 0.4))
    pause_sec = sum(p.duration_ms for p in pauses) / 1000.0
    return round(max(0.6, base + pause_sec + 0.15), 3)
