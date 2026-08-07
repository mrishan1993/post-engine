from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from db.models import TrendSignal, TrendTopic, TrendTopicSignal


def assign_one_to_one_topics(
    session: Session,
    signals: list[TrendSignal],
    *,
    vertical_routing: dict[str, Any],
) -> list[TrendTopic]:
    """Phase-1: keyword-bucket topics (not full LLM clustering yet).

    Signals sharing a strong keyword from vertical routing are grouped so
    cross-source confirmation can fire before the LLM clustering step lands.
    """
    buckets: dict[str, list[TrendSignal]] = {}
    for signal in signals:
        key = _bucket_key(signal, vertical_routing)
        buckets.setdefault(key, []).append(signal)

    topics: list[TrendTopic] = []
    now = datetime.now(timezone.utc)
    for key, group in buckets.items():
        primary = group[0]
        label = _label_for_group(group, key)
        verticals = _route_verticals_for_group(group, vertical_routing)
        topic = TrendTopic(
            topic_label=label[:256],
            description=_describe_group(group),
            candidate_verticals=verticals,
            first_seen_at=now,
            last_seen_at=now,
            status="active",
        )
        session.add(topic)
        session.flush()
        for signal in group:
            session.add(TrendTopicSignal(topic_id=topic.id, signal_id=signal.id))
        topics.append(topic)
    session.flush()
    return topics


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _bucket_key(signal: TrendSignal, routing: dict[str, Any]) -> str:
    text = f"{signal.title_or_query or ''} {' '.join((signal.raw_metrics or {}).get('tags') or [])}"
    tokens = _tokens(text)
    # Prefer a configured vertical keyword as the bucket
    for slug, rules in routing.items():
        for kw in rules.get("keywords", []):
            kw_l = kw.lower()
            if kw_l in text.lower() or set(kw_l.split()) <= tokens:
                return f"{slug}:{kw_l}"
    # Fall back to first meaningful token so unrelated items don't all merge
    if tokens:
        return f"misc:{sorted(tokens)[0]}"
    return f"misc:{signal.id}"


def _label_for_group(group: list[TrendSignal], key: str) -> str:
    yt = next((s for s in group if s.source == "youtube"), None)
    if yt and yt.title_or_query:
        return yt.title_or_query
    return group[0].title_or_query or key


def _describe_group(group: list[TrendSignal]) -> str:
    parts = [_describe(s) for s in group]
    sources = sorted({s.source for s in group})
    return f"Sources={','.join(sources)}. " + " | ".join(parts)


def _describe(signal: TrendSignal) -> str:
    metrics = signal.raw_metrics or {}
    if signal.source == "youtube":
        return (
            f"YT({signal.region}): {metrics.get('views', 0)} views, "
            f"vel={float(metrics.get('velocity_views_per_hour') or 0):.0f}/hr"
        )
    if signal.source == "google_trends":
        return (
            f"GT: interest={metrics.get('interest_latest')}, "
            f"rising={float(metrics.get('rising_ratio') or 0):.2f}"
        )
    return f"{signal.source}"


def _route_verticals_for_group(
    group: list[TrendSignal], routing: dict[str, Any]
) -> list[str]:
    matched: set[str] = set()
    for signal in group:
        matched.update(_route_verticals(signal, routing))
    return sorted(matched) if matched else sorted(routing.keys())


def _route_verticals(signal: TrendSignal, routing: dict[str, Any]) -> list[str]:
    text = f"{signal.title_or_query or ''} {' '.join((signal.raw_metrics or {}).get('tags') or [])}".lower()
    category = str(signal.category or "")
    matched: list[str] = []
    for slug, rules in routing.items():
        keywords = [k.lower() for k in rules.get("keywords", [])]
        yt_cats = [str(c) for c in rules.get("youtube_categories", [])]
        keyword_hit = any(k in text for k in keywords)
        category_name_hit = category in yt_cats
        if keyword_hit or category_name_hit:
            matched.append(slug)
    return matched
