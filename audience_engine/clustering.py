from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


TOPIC_RULES: list[tuple[str, list[str]]] = [
    ("character_relationships", ["meet", "together", "pairing", "+", "and character", "relationship", "ship"]),
    ("story_predictions", ["i think", "theory", "going to", "prediction", "ending"]),
    ("product_questions", ["buy", "price", "link", "where can"]),
    ("memes", ["😂", "🤣", "meme", "edit this", "sound"]),
    ("negative_feedback", ["boring", "waste", "confusing", "hate", "cringe"]),
    ("format_requests", ["longer", "part 2", "episode", "series", "format"]),
    ("character_return", ["bring back", "where is", "wapas lao", "we want"]),
]


def cluster_topics(interactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Heuristic topic clustering from classified interactions (no ML deps)."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ix in interactions:
        if ix.get("is_noise"):
            continue
        text = (ix.get("text") or ix.get("text_reference") or "").lower()
        entities = ix.get("entities") or {}
        assigned = None
        if entities.get("pairing"):
            assigned = "character_relationships"
        else:
            for topic, cues in TOPIC_RULES:
                if any(c in text for c in cues):
                    assigned = topic
                    break
        if not assigned:
            chars = entities.get("characters") or []
            if chars:
                assigned = f"character_{chars[0]}"
            elif ix.get("intent_type") == "content_request":
                assigned = "format_requests"
            else:
                assigned = "general"
        buckets[assigned].append(ix)

    topics: list[dict[str, Any]] = []
    for topic, items in buckets.items():
        if topic == "general" and len(items) < 3:
            continue
        sentiments = [i.get("sentiment") or "neutral" for i in items]
        pos = sentiments.count("positive")
        neg = sentiments.count("negative")
        neu = len(sentiments) - pos - neg
        total = max(1, len(sentiments))
        keywords = _keywords([i.get("text") or i.get("text_reference") or "" for i in items])
        topics.append(
            {
                "topic": topic,
                "volume": len(items),
                "velocity": round(len(items) / max(1, total) * len(items), 3),
                "sentiment": {
                    "positive": round(pos / total, 3),
                    "neutral": round(neu / total, 3),
                    "negative": round(neg / total, 3),
                },
                "keywords": keywords,
                "related_content": list(
                    {i.get("content_id") for i in items if i.get("content_id")}
                ),
                "evidence_count": len(items),
            }
        )
    topics.sort(key=lambda t: t["volume"], reverse=True)
    return topics


def aggregate_demands(
    interactions: list[dict[str, Any]],
    *,
    min_volume: int = 5,
) -> list[dict[str, Any]]:
    """Aggregate recurring requests into audience demands."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ix in interactions:
        if ix.get("is_noise"):
            continue
        intent = ix.get("intent_type")
        entities = ix.get("entities") or {}
        text = (ix.get("text") or ix.get("text_reference") or "").lower()
        key = None
        dtype = "other"
        subject = None
        action = "create_content"

        if entities.get("pairing"):
            key = f"pair:{entities['pairing']}"
            dtype = "character_pairing"
            subject = f"Character pairing {entities['pairing'].replace('+', ' + ')}"
            action = "create_episode"
        elif intent == "character_request":
            chars = entities.get("characters") or []
            if chars:
                key = f"char:{chars[0]}"
                subject = f"Bring back {chars[0]}"
            else:
                m = re.search(r"bring\s+(?:back\s+)?(\w+)", text)
                key = f"char:{m.group(1) if m else 'unknown'}"
                subject = text[:80]
            dtype = "new_character" if "new" in text else "character_pairing"
            # character return is closer to story continuation / character request
            dtype = "story_continuation"
            action = "create_episode"
        elif intent == "content_request":
            if "longer" in text:
                key = "format:longer_episodes"
                dtype = "format"
                subject = "Longer episodes"
            else:
                key = f"content:{normalize_subject(text)}"
                dtype = "topic"
                subject = text[:80]
            action = "create_content"
        elif intent == "participation":
            key = "participation:poll"
            dtype = "challenge"
            subject = "Audience participation / poll"
            action = "create_poll"

        if key and subject:
            groups[key].append({**ix, "_subject": subject, "_dtype": dtype, "_action": action})

    demands = []
    for key, items in groups.items():
        vol = len(items)
        if vol < min_volume:
            continue
        conf = min(0.98, 0.6 + 0.03 * vol + 0.1 * min(1.0, vol / 30))
        velocity = min(0.99, vol / 15.0)
        strategic = 0.9 if items[0]["_dtype"] in {"character_pairing", "story_continuation"} else 0.7
        sentiments = [i.get("sentiment") for i in items]
        dominant = max(set(sentiments), key=sentiments.count) if sentiments else "positive"
        demands.append(
            {
                "subject": items[0]["_subject"],
                "type": items[0]["_dtype"],
                "volume": vol,
                "velocity": round(velocity, 3),
                "confidence": round(conf, 3),
                "strategic_fit": strategic,
                "recommended_action": items[0]["_action"],
                "sentiment": dominant,
                "audience_segments": ["core_fans", "returning_viewers"],
                "evidence": {
                    "key": key,
                    "evidence_count": vol,
                    "sample_texts": [
                        (i.get("text") or i.get("text_reference") or "")[:120] for i in items[:5]
                    ],
                    "source_quality": "public_comments",
                    "recency": "batch",
                    "consistency": round(min(1.0, vol / 10), 3),
                },
                "related_content": list({i.get("content_id") for i in items if i.get("content_id")}),
            }
        )
    demands.sort(key=lambda d: d["volume"] * (d["confidence"] or 0), reverse=True)
    return demands


def normalize_subject(text: str) -> str:
    t = re.sub(r"[^a-z0-9\s]", "", text.lower())
    return "_".join(t.split()[:6]) or "request"


def _keywords(texts: list[str], *, limit: int = 8) -> list[str]:
    stop = {
        "the",
        "a",
        "an",
        "is",
        "to",
        "and",
        "of",
        "for",
        "in",
        "this",
        "that",
        "with",
        "i",
        "you",
        "we",
        "my",
        "it",
    }
    counts: dict[str, int] = defaultdict(int)
    for t in texts:
        for w in re.findall(r"[a-zA-Z']{3,}", t.lower()):
            if w not in stop:
                counts[w] += 1
    return [w for w, _ in sorted(counts.items(), key=lambda x: -x[1])[:limit]]


def character_affinity_from_interactions(
    interactions: list[dict[str, Any]],
    characters: list[str],
) -> list[dict[str, Any]]:
    out = []
    for c in characters:
        slug = c.lower().replace(" ", "_")
        relevant = []
        for ix in interactions:
            if ix.get("is_noise"):
                continue
            ents = ix.get("entities") or {}
            text = (ix.get("text") or ix.get("text_reference") or "").lower()
            if slug in (ents.get("characters") or []) or slug.replace("_", " ") in text:
                relevant.append(ix)
        if not relevant:
            continue
        pos = sum(1 for i in relevant if i.get("sentiment") == "positive")
        neg = sum(1 for i in relevant if i.get("sentiment") == "negative")
        total = len(relevant)
        affinity = round((pos - neg) / total * 50 + 50 + min(20, total), 2)
        relationships = {}
        for ix in relevant:
            pair = (ix.get("entities") or {}).get("pairing")
            if pair and slug in pair:
                relationships[pair] = relationships.get(pair, 0) + 1
        out.append(
            {
                "character_slug": slug,
                "affinity_score": affinity,
                "sentiment": {
                    "positive": round(pos / total, 3),
                    "negative": round(neg / total, 3),
                    "neutral": round((total - pos - neg) / total, 3),
                },
                "trend": "up" if pos > neg else "down" if neg > pos else "flat",
                "relationships": relationships,
                "audience_requests": [
                    (i.get("text") or "")[:80]
                    for i in relevant
                    if i.get("intent_type") in {"character_request", "content_request"}
                ][:5],
            }
        )
    return out
