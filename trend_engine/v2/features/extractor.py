from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from db.models import (
    AudioPattern,
    CommentSentiment,
    ContentFeature,
    EmotionVector,
    HookLibrary,
    RawContent,
    StoryPattern,
    VisualPattern,
)

EMOTIONS = ["fear", "joy", "curiosity", "anger", "surprise", "disgust", "sadness", "hope", "relief"]

HOOK_RULES: list[tuple[str, list[str]]] = [
    ("question", [r"\?", r"\bwhy\b", r"\bwhat if\b"]),
    ("shock", [r"\bnever\b", r"\baccidentally\b", r"\bscream\b"]),
    ("curiosity", [r"\bsecret\b", r"\bmystery\b", r"\bopened\b"]),
    ("fear", [r"\bghost\b", r"\bhorror\b", r"\bhaunted\b", r"\bdark\b"]),
    ("relatability", [r"\bwhen you\b", r"\beveryone\b", r"\bparents\b"]),
    ("open_loop", [r"\bi should never\b", r"\buntil\b", r"\bpart \d\b"]),
]


def extract_content_dna(
    session: Session,
    items: list[RawContent],
    *,
    lexicon: dict[str, list[str]] | None = None,
) -> list[ContentFeature]:
    """Layer 2: every item → structured Content DNA + pattern library rows."""
    lexicon = lexicon or {}
    features: list[ContentFeature] = []
    for item in items:
        text = f"{item.title or ''} {item.description or ''}"
        meta = item.platform_metadata or {}
        hook = _extract_hook(text)
        story = _extract_story(text)
        emotion = _extract_emotion(text, lexicon)
        visual = _extract_visual(text, meta)
        audio = _extract_audio(text, meta)
        editing = _extract_editing(text, meta)
        velocity = _extract_velocity(meta)
        comments = _extract_comments(text, meta)

        feat = ContentFeature(
            raw_content_id=item.id,
            duration_sec=int(meta.get("duration_sec") or meta.get("age_hours") or 60),
            hook=hook,
            story_arc=story,
            emotion=emotion,
            visual_style=visual,
            audio_style=audio,
            editing_style=editing,
            format=_infer_format(text, story),
            audience=_infer_audience(text),
            topics=_infer_topics(text),
            hashtags=list(meta.get("tags") or [])[:12],
            cta=_infer_cta(text),
            velocity=velocity,
        )
        session.add(feat)
        session.flush()

        session.add(
            EmotionVector(
                raw_content_id=item.id,
                scores=emotion.get("scores"),
                dominant=emotion.get("dominant"),
                progression=emotion.get("progression") or [],
            )
        )
        session.add(
            CommentSentiment(
                raw_content_id=item.id,
                summary=comments.get("summary"),
                requests=comments.get("requests") or [],
                questions=comments.get("questions") or [],
                sentiment_scores=comments.get("sentiment_scores"),
                future_opportunities=comments.get("future_opportunities") or [],
            )
        )
        session.add(
            HookLibrary(
                hook_type=hook.get("hook_type") or "unknown",
                example_text=hook.get("first_sentence"),
                emotion=emotion.get("dominant"),
                source_feature_id=feat.id,
            )
        )
        session.add(
            StoryPattern(
                pattern_name=story.get("pattern") or "unknown",
                beats=story,
                source_feature_id=feat.id,
            )
        )
        session.add(
            VisualPattern(
                pattern_name=visual.get("style") or "unknown",
                features=visual,
                meme_type=visual.get("meme_type"),
                source_feature_id=feat.id,
            )
        )
        session.add(
            AudioPattern(
                pattern_name=audio.get("style") or "unknown",
                features=audio,
                meme_type=audio.get("meme_type"),
                source_feature_id=feat.id,
            )
        )
        features.append(feat)
    session.flush()
    return features


def _extract_hook(text: str) -> dict[str, Any]:
    lowered = text.lower()
    hook_type = "curiosity"
    for name, patterns in HOOK_RULES:
        if any(re.search(p, lowered) for p in patterns):
            hook_type = name
            break
    first = (text.strip().split(".")[0] or text.strip())[:160]
    return {
        "hook_type": hook_type,
        "first_sentence": first,
        "first_3_seconds": first[:80],
        "open_loop": bool(re.search(r"\bi should never\b|\buntil\b|\?", lowered)),
        "urgency": bool(re.search(r"\bnow\b|\bhurry\b|\baccidentally\b", lowered)),
        "first_person": bool(re.search(r"\bi\b|\bpov\b", lowered)),
    }


def _extract_story(text: str) -> dict[str, Any]:
    lowered = text.lower()
    pattern = "linear"
    if "pov" in lowered or re.search(r"\bi accidentally\b", lowered):
        pattern = "pov"
    elif re.search(r"\btwist\b|\bnever knew\b", lowered):
        pattern = "twist"
    elif re.search(r"\brhyme\b|\bsong\b|\babc\b|\bcolors?\b", lowered):
        pattern = "rhyme_loop"
    return {
        "pattern": pattern,
        "cold_open": pattern in {"pov", "twist"},
        "setup": True,
        "conflict": pattern in {"pov", "twist"},
        "escalation": pattern == "twist",
        "twist": pattern == "twist",
        "resolution": pattern == "rhyme_loop",
        "cta": bool(re.search(r"\bsubscribe\b|\bpart 2\b|\bfollow\b", lowered)),
    }


def _extract_emotion(text: str, lexicon: dict[str, list[str]]) -> dict[str, Any]:
    lowered = text.lower()
    scores = {e: 0.05 for e in EMOTIONS}
    for emotion, words in lexicon.items():
        if emotion not in scores:
            continue
        hits = sum(1 for w in words if w in lowered)
        if hits:
            scores[emotion] = min(0.2 + 0.15 * hits, 1.0)
    # title heuristics
    if any(w in lowered for w in ("horror", "scary", "ghost", "haunted")):
        scores["fear"] = max(scores["fear"], 0.85)
        scores["surprise"] = max(scores["surprise"], 0.45)
    if any(w in lowered for w in ("kids", "rhyme", "colors", "abc", "happy")):
        scores["joy"] = max(scores["joy"], 0.8)
        scores["hope"] = max(scores["hope"], 0.4)
    if "?" in text or "what" in lowered:
        scores["curiosity"] = max(scores["curiosity"], 0.55)
    dominant = max(scores, key=scores.get)
    progression = [dominant]
    if scores.get("curiosity", 0) > 0.4 and dominant != "curiosity":
        progression = ["curiosity", dominant]
    if dominant == "fear":
        progression = ["curiosity", "fear", "relief"]
    return {"scores": scores, "dominant": dominant, "progression": progression}


def _extract_visual(text: str, meta: dict[str, Any]) -> dict[str, Any]:
    lowered = text.lower()
    meme = None
    for token in ("pov", "npc", "sigma", "aura", "brainrot"):
        if token in lowered:
            meme = token
            break
    return {
        "style": "character_rig" if "kids" in lowered else ("dark_still" if "horror" in lowered or "scary" in lowered else "mixed"),
        "avg_cuts_per_10s": 4 if meme == "pov" else 2,
        "zoom_frequency": "medium" if meme == "pov" else "low",
        "subtitle_density": "high",
        "caption_style": "large_yellow" if "kids" in lowered else "subtle_white",
        "face_presence": False,
        "animation": "kids" in lowered or "rhyme" in lowered,
        "color_palette": "bright" if "kids" in lowered else "desaturated",
        "meme_type": meme,
        "tags": meta.get("tags") or [],
    }


def _extract_audio(text: str, meta: dict[str, Any]) -> dict[str, Any]:
    lowered = text.lower()
    if any(w in lowered for w in ("horror", "scary", "ghost")):
        return {
            "style": "low_bass_narration",
            "narration": True,
            "ai_voice": True,
            "music_genre": "dark ambient",
            "tempo_bpm": 70,
            "silence_used": True,
            "sound_effects": True,
            "beat_drops": False,
            "meme_type": None,
        }
    return {
        "style": "cheerful_narration",
        "narration": True,
        "ai_voice": True,
        "music_genre": "kids upbeat",
        "tempo_bpm": 110,
        "silence_used": False,
        "sound_effects": True,
        "beat_drops": True,
        "meme_type": None,
    }


def _extract_editing(text: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "pace": "fast" if "pov" in text.lower() else "medium",
        "transitions": "hard_cut",
        "text_overlay": True,
    }


def _extract_velocity(meta: dict[str, Any]) -> dict[str, Any]:
    views = float(meta.get("views") or 0)
    age = max(float(meta.get("age_hours") or 24), 0.5)
    likes = float(meta.get("likes") or 0)
    comments = float(meta.get("comments") or 0)
    return {
        "views_per_hour": views / age,
        "likes_per_hour": likes / age,
        "comments_per_hour": comments / age,
        "shares_per_hour": 0.0,
        "subscribers_gained_per_hour": 0.0,
        "interest_latest": meta.get("interest_latest"),
        "rising_ratio": meta.get("rising_ratio"),
    }


def _extract_comments(text: str, meta: dict[str, Any]) -> dict[str, Any]:
    # Stub comment intelligence until Comments API is wired
    requests: list[str] = []
    opportunities: list[str] = []
    lowered = text.lower()
    if "horror" in lowered or "scary" in lowered:
        requests = ["Part 2 please", "Tell more"]
        opportunities = ["Sequel / Part 2", "Same format, new setting"]
    if "krishna" in lowered or "myth" in lowered:
        requests = ["Do Krishna next"]
        opportunities = ["Indian mythology series"]
    if "colors" in lowered or "abc" in lowered:
        requests = ["More songs like this"]
        opportunities = ["Series: shapes, animals, numbers"]
    positive = 0.82 if requests else 0.65
    return {
        "summary": {"positive": positive, "negative": 1 - positive, "sample_size": "stub"},
        "requests": requests,
        "questions": ["What happens next?"] if requests else [],
        "sentiment_scores": {"positive": positive, "negative": round(1 - positive, 2), "requests": len(requests)},
        "future_opportunities": opportunities,
    }


def _infer_format(text: str, story: dict[str, Any]) -> str:
    if story.get("pattern") == "pov":
        return "pov_short"
    if story.get("pattern") == "rhyme_loop":
        return "kids_rhyme_short"
    return "narration_short"


def _infer_audience(text: str) -> str:
    lowered = text.lower()
    if any(w in lowered for w in ("kids", "toddler", "nursery", "abc", "colors")):
        return "2-8 with parents"
    if any(w in lowered for w in ("horror", "scary", "creepy")):
        return "16-24"
    return "general"


def _infer_topics(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z]{4,}", text.lower())
    stop = {"with", "that", "this", "from", "your", "story", "short", "video"}
    return [t for t in tokens if t not in stop][:8]


def _infer_cta(text: str) -> str | None:
    if re.search(r"part \d|subscribe|follow", text.lower()):
        return "Follow for part 2"
    return "Watch till the end"
