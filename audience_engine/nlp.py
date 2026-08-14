from __future__ import annotations

import re
from typing import Any


# Devanagari block presence → Hindi
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# Common Hinglish / Hindi romanized tokens
_HINGLISH = {
    "bhai",
    "yaar",
    "kya",
    "hai",
    "nahi",
    "nahin",
    "wapas",
    "lao",
    "karo",
    "matlab",
    "sach",
    "bahut",
    "accha",
    "achha",
    "mazza",
    "mazzaa",
    "scene",
    "full",
    "on",
}

SPAM_PATTERNS = [
    re.compile(r"(?:https?://|www\.)\S+", re.I),
    re.compile(r"(?:follow\s*me|check\s*my\s*bio|dm\s*for\s*(?:promo|collab))", re.I),
    re.compile(r"(?:crypto|forex|giveaway|free\s*followers)", re.I),
    re.compile(r"(.)\1{6,}"),  # aaaaaaaa
]

INTENT_PATTERNS: list[tuple[str, list[re.Pattern[str]]]] = [
    (
        "character_request",
        [
            re.compile(r"\bbring\s+(?:back\s+)?(?:character\s+)?[a-z0-9_]+\b", re.I),
            re.compile(r"\bwhere\s+is\s+(?:character\s+)?[a-z0-9_]+\b", re.I),
            re.compile(r"\bwapas\s+lao\b", re.I),
            re.compile(r"\bwe\s+want\s+[a-z0-9_]+\b", re.I),
        ],
    ),
    (
        "content_request",
        [
            re.compile(r"\bmake\s+(?:another|more|one)\b", re.I),
            re.compile(r"\bneed\s+(?:a\s+)?(?:longer|part\s*2|sequel)\b", re.I),
            re.compile(r"\blonger\s+episodes?\b", re.I),
            re.compile(r"\bdo\s+(?:a|another)\s+(?:collab|challenge)\b", re.I),
        ],
    ),
    (
        "purchase_intent",
        [
            re.compile(r"\bwhere\s+(?:can\s+i\s+)?buy\b", re.I),
            re.compile(r"\blink\s+(?:please|pls)?\b", re.I),
            re.compile(r"\bprice\b", re.I),
        ],
    ),
    (
        "information_seeking",
        [
            re.compile(r"\bhow\s+(?:does|do|did)\b", re.I),
            re.compile(r"\bwhat\s+(?:happens|is|does)\b", re.I),
            re.compile(r"\bexplain\b", re.I),
            re.compile(r"\bkya\s+matlab\b", re.I),
        ],
    ),
    (
        "complaint",
        [
            re.compile(r"\bdoesn'?t\s+make\s+sense\b", re.I),
            re.compile(r"\bboring\b", re.I),
            re.compile(r"\bwaste\b", re.I),
            re.compile(r"\bconfusing\b", re.I),
        ],
    ),
    (
        "praise",
        [
            re.compile(r"\bfunniest\b", re.I),
            re.compile(r"\blove\s+this\b", re.I),
            re.compile(r"\bgold\b", re.I),
            re.compile(r"\bbest\b", re.I),
            re.compile(r"\b😂|🤣|🔥\b"),
            re.compile(r"\bmazza\b", re.I),
        ],
    ),
    (
        "participation",
        [
            re.compile(r"\bcan\s+i\s+be\s+in\b", re.I),
            re.compile(r"\bvote\b", re.I),
            re.compile(r"\blet\s+us\s+choose\b", re.I),
        ],
    ),
    (
        "prediction",
        [
            re.compile(r"\bi\s+think\b", re.I),
            re.compile(r"\bgoing\s+to\b", re.I),
            re.compile(r"\btheory\b", re.I),
        ],
    ),
    (
        "emotional_attachment",
        [
            re.compile(r"\bfeel\s+bad\b", re.I),
            re.compile(r"\bcry(?:ing)?\b", re.I),
            re.compile(r"\battach(?:ed)?\b", re.I),
        ],
    ),
    (
        "conflict",
        [
            re.compile(r"\b(?:is\s+)?(?:clearly\s+)?better\b", re.I),
            re.compile(r"\bvs\b", re.I),
            re.compile(r"\bworse\b", re.I),
        ],
    ),
]

POSITIVE = {
    "love",
    "best",
    "funny",
    "funniest",
    "gold",
    "amazing",
    "great",
    "fire",
    "iconic",
    "accha",
    "mazza",
    "😂",
    "🤣",
    "🔥",
    "❤️",
}
NEGATIVE = {
    "hate",
    "boring",
    "waste",
    "confusing",
    "bad",
    "worst",
    "cringe",
    "stupid",
    "nahi",
}
EMOTION_MAP: list[tuple[str, list[str]]] = [
    ("amusement", ["😂", "🤣", "funny", "funniest", "lol", "mazza", "haha"]),
    ("excitement", ["🔥", "can't wait", "excited", "hype", "yess"]),
    ("curiosity", ["how", "what", "why", "kya", "explain", "?"]),
    ("anger", ["hate", "angry", "furious", "worst"]),
    ("confusion", ["confusing", "doesn't make sense", "huh", "matlab"]),
    ("surprise", ["wait", "unexpected", "shock", "omg"]),
    ("sadness", ["sad", "feel bad", "cry", "😭"]),
    ("attachment", ["love", "miss", "bring back", "wapas", "❤️"]),
    ("frustration", ["again?", "stop", "enough", "boring"]),
]

MODERATION_PATTERNS = [
    ("spam", re.compile(r"(?:crypto|forex|free\s*followers|dm\s*for\s*promo)", re.I)),
    ("harassment", re.compile(r"\b(?:kill\s+yourself|kys)\b", re.I)),
    ("hate", re.compile(r"\b(?:slur_placeholder)\b", re.I)),  # placeholder — expand carefully
]


def detect_language(text: str) -> str:
    if _DEVANAGARI.search(text):
        return "hi"
    tokens = set(re.findall(r"[a-zA-Z']+", text.lower()))
    if tokens & _HINGLISH:
        return "hinglish"
    return "en"


def normalize_text(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def is_spam_or_noise(text: str, *, seen_normalized: set[str] | None = None) -> tuple[bool, str | None]:
    norm = normalize_text(text)
    if len(norm) < 2:
        return True, "too_short"
    if seen_normalized is not None and norm in seen_normalized:
        return True, "duplicate"
    for pat in SPAM_PATTERNS:
        if pat.search(text):
            return True, "spam_pattern"
    # engagement bait
    if re.fullmatch(r"(?:first|f|nice|cool|🔥)+", norm):
        return True, "low_signal"
    return False, None


def classify_intent(text: str) -> tuple[str, float]:
    for intent, patterns in INTENT_PATTERNS:
        for pat in patterns:
            if pat.search(text):
                return intent, 0.85
    if "?" in text:
        return "information_seeking", 0.55
    return "other", 0.4


def classify_sentiment(text: str) -> str:
    tokens = set(re.findall(r"[a-zA-Z']+|[\U0001F300-\U0001FAFF]", text.lower()))
    # also raw emoji substrings
    pos = sum(1 for w in POSITIVE if w in text.lower())
    neg = sum(1 for w in NEGATIVE if w in text.lower())
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def classify_emotion(text: str) -> str:
    low = text.lower()
    for emotion, cues in EMOTION_MAP:
        if any(c in low for c in cues):
            return emotion
    return "neutral"


def extract_entities(text: str, characters: list[str]) -> dict[str, Any]:
    low = text.lower()
    found = []
    for c in characters:
        slug = c.lower().replace(" ", "_")
        name = c.lower().replace("_", " ")
        letter = slug.split("_")[-1]
        if (
            slug in low
            or name in low
            or f"character {letter}" in low
            or re.search(rf"\bcharacter\s+{re.escape(letter)}\b", low)
        ):
            if slug not in found:
                found.append(slug)
    pairing = None
    m = re.search(r"character\s+([a-z0-9_]+)\s*\+\s*character\s+([a-z0-9_]+)", low)
    if m:
        pairing = f"character_{m.group(1)}+character_{m.group(2)}"
    elif re.search(r"character\s+([a-z0-9_]+)\s+meet(?:s)?\s+character\s+([a-z0-9_]+)", low):
        m2 = re.search(r"character\s+([a-z0-9_]+)\s+meet(?:s)?\s+character\s+([a-z0-9_]+)", low)
        assert m2
        pairing = f"character_{m2.group(1)}+character_{m2.group(2)}"
    elif re.search(r"character\s+([a-z0-9_]+)\s+and\s+character\s+([a-z0-9_]+)", low):
        m3 = re.search(r"character\s+([a-z0-9_]+)\s+and\s+character\s+([a-z0-9_]+)", low)
        assert m3
        pairing = f"character_{m3.group(1)}+character_{m3.group(2)}"
    elif len(found) >= 2:
        pairing = "+".join(sorted(found[:2]))
    return {"characters": found, "pairing": pairing}


def moderation_flags(text: str) -> list[str]:
    flags = []
    for name, pat in MODERATION_PATTERNS:
        if pat.search(text):
            flags.append(name)
    return flags


def comment_priority(
    *,
    intent: str,
    sentiment: str,
    likes: int,
    is_request: bool,
    strategic: bool,
) -> float:
    score = 0.2
    if intent in {"character_request", "content_request", "purchase_intent"}:
        score += 0.35
    if is_request:
        score += 0.15
    if strategic:
        score += 0.2
    if sentiment == "negative" and intent == "complaint":
        score += 0.15
    score += min(0.15, likes / 100.0)
    return round(min(1.0, score), 3)


def analyze_comment(
    text: str,
    *,
    characters: list[str],
    likes: int = 0,
    seen_normalized: set[str] | None = None,
) -> dict[str, Any]:
    noise, reason = is_spam_or_noise(text, seen_normalized=seen_normalized)
    lang = detect_language(text)
    intent, intent_conf = classify_intent(text)
    sentiment = classify_sentiment(text)
    emotion = classify_emotion(text)
    entities = extract_entities(text, characters)
    flags = moderation_flags(text)
    is_request = intent in {"character_request", "content_request", "participation"}
    strategic = bool(entities.get("characters") or entities.get("pairing"))
    priority = 0.05 if noise else comment_priority(
        intent=intent,
        sentiment=sentiment,
        likes=likes,
        is_request=is_request,
        strategic=strategic,
    )
    return {
        "text_normalized": normalize_text(text),
        "language": lang,
        "is_noise": noise,
        "noise_reason": reason,
        "intent_type": intent,
        "intent_confidence": intent_conf,
        "sentiment": sentiment,
        "emotion": emotion,
        "entities": entities,
        "moderation_flags": flags,
        "priority": priority,
    }
