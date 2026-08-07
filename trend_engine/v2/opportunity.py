from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    CommentSentiment,
    ContentFeature,
    OpportunityScore,
    RawContent,
    TrendLifecycle,
)
from trend_engine.v2.patterns.lifecycle import pattern_key_for


DEFAULT_WEIGHTS = {
    "virality": 0.18,
    "novelty": 0.12,
    "growth": 0.18,
    "competition": 0.08,
    "brand_fit": 0.10,
    "character_fit": 0.12,
    "audience_fit": 0.08,
    "posting_time": 0.04,
    "platform_fit": 0.05,
    "historical_success": 0.05,
}


@dataclass
class RankedOpportunity:
    vertical_slug: str
    title: str
    score: float
    breakdown: dict[str, float]
    payload: dict[str, Any]
    lifecycle_stage: str
    pattern_key: str


def rank_opportunities(
    session: Session,
    pairs: list[tuple[RawContent, ContentFeature]],
    *,
    vertical_slug: str,
    vertical_cfg: dict[str, Any],
    characters: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
    reject_stages: list[str] | None = None,
    min_score: float = 55,
    max_results: int = 5,
) -> list[RankedOpportunity]:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    reject_stages = reject_stages or ["saturated", "declining", "dead"]
    preferred_emotions = set(vertical_cfg.get("emotions_preferred") or [])
    audience_target = vertical_cfg.get("audience") or ""

    ranked: list[RankedOpportunity] = []
    for raw, feat in pairs:
        key = pattern_key_for(feat, raw)
        life = session.scalar(select(TrendLifecycle).where(TrendLifecycle.pattern_key == key))
        stage = life.stage if life else "emerging"
        if stage in reject_stages:
            continue

        comments = session.scalar(
            select(CommentSentiment)
            .where(CommentSentiment.raw_content_id == raw.id)
            .limit(1)
        )
        breakdown = _score_dimensions(
            raw,
            feat,
            life,
            comments,
            preferred_emotions=preferred_emotions,
            audience_target=audience_target,
            has_characters=bool(characters),
        )
        score = 100.0 * sum(breakdown[k] * weights.get(k, 0.0) for k in weights)
        if score < min_score:
            continue

        why = _why_viral(feat, life, comments)
        payload = {
            "trend": _trend_label(feat, raw),
            "lifecycle": stage,
            "platforms": list(life.platforms) if life else [raw.source],
            "emotion": (feat.emotion or {}).get("dominant"),
            "hook": (feat.hook or {}).get("first_sentence"),
            "hook_type": (feat.hook or {}).get("hook_type"),
            "story_pattern": (feat.story_arc or {}).get("pattern"),
            "editing_style": (feat.editing_style or {}).get("pace"),
            "audio": (feat.audio_style or {}).get("style"),
            "visual": (feat.visual_style or {}).get("style"),
            "target_audience": feat.audience,
            "format": feat.format,
            "why_viral": why,
            "comment_requests": list(comments.requests) if comments else [],
            "future_from_comments": list(comments.future_opportunities) if comments else [],
            "source_title": raw.title,
            "source": raw.source,
            "confidence": float(life.confidence) if life else 0.4,
        }
        ranked.append(
            RankedOpportunity(
                vertical_slug=vertical_slug,
                title=payload["trend"][:256],
                score=round(score, 2),
                breakdown={k: round(v, 3) for k, v in breakdown.items()},
                payload=payload,
                lifecycle_stage=stage,
                pattern_key=key,
            )
        )

    ranked.sort(key=lambda o: o.score, reverse=True)
    return ranked[:max_results]


def persist_opportunities(
    session: Session, opportunities: list[RankedOpportunity]
) -> list[OpportunityScore]:
    rows: list[OpportunityScore] = []
    for opp in opportunities:
        row = OpportunityScore(
            vertical_slug=opp.vertical_slug,
            title=opp.title,
            score=opp.score,
            score_breakdown=opp.breakdown,
            opportunity=opp.payload,
            lifecycle_stage=opp.lifecycle_stage,
            pattern_key=opp.pattern_key,
            content_brief_ids=[],
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _score_dimensions(
    raw: RawContent,
    feat: ContentFeature,
    life: TrendLifecycle | None,
    comments: CommentSentiment | None,
    *,
    preferred_emotions: set[str],
    audience_target: str,
    has_characters: bool,
) -> dict[str, float]:
    vph = float((feat.velocity or {}).get("views_per_hour") or 0)
    virality = min(vph / 50_000.0, 1.0)
    growth = 0.5
    if life and life.metrics:
        growth = min(float(life.metrics.get("weekly_growth_pct") or 0) / 300.0, 1.0)
    novelty = 0.85 if (life and life.stage in {"emerging", "growing"}) else 0.35
    competition = 0.7 if (life and int((life.metrics or {}).get("sample_size") or 1) < 6) else 0.4
    dominant = (feat.emotion or {}).get("dominant")
    brand_fit = 0.9 if dominant in preferred_emotions else 0.35
    character_fit = 0.85 if has_characters and brand_fit > 0.5 else 0.4
    audience_fit = 0.9 if audience_target and feat.audience == audience_target else 0.55
    posting_time = 0.6  # placeholder until historical memory learns windows
    platform_fit = min(0.4 + 0.2 * len(life.platforms if life else [raw.source]), 1.0)
    historical_success = 0.5  # V3 learns this from viral_predictions
    if comments and comments.future_opportunities:
        growth = min(growth + 0.1, 1.0)
        novelty = min(novelty + 0.05, 1.0)
    return {
        "virality": virality,
        "novelty": novelty,
        "growth": growth,
        "competition": competition,
        "brand_fit": brand_fit,
        "character_fit": character_fit,
        "audience_fit": audience_fit,
        "posting_time": posting_time,
        "platform_fit": platform_fit,
        "historical_success": historical_success,
    }


def _trend_label(feat: ContentFeature, raw: RawContent) -> str:
    emotion = (feat.emotion or {}).get("dominant") or "emotion"
    story = (feat.story_arc or {}).get("pattern") or "story"
    return f"{story.replace('_', ' ').title()} / {emotion.title()}"


def _why_viral(
    feat: ContentFeature,
    life: TrendLifecycle | None,
    comments: CommentSentiment | None,
) -> list[str]:
    reasons: list[str] = []
    if life and life.metrics:
        g = life.metrics.get("weekly_growth_pct")
        if g:
            reasons.append(f"{g:.0f}% weekly growth signal")
        reasons.append(f"Lifecycle: {life.stage} (not saturated)")
        if len(life.platforms or []) >= 2:
            reasons.append(f"Cross-platform: {', '.join(life.platforms)}")
    vph = (feat.velocity or {}).get("views_per_hour")
    if vph:
        reasons.append(f"Velocity ~{float(vph):.0f} views/hour")
    if comments and comments.summary:
        pos = (comments.summary or {}).get("positive")
        if pos:
            reasons.append(f"{float(pos)*100:.0f}% positive engagement (stub/heuristic)")
    if comments and comments.requests:
        reasons.append(f"Comments requesting: {comments.requests[0]}")
    return reasons or ["Pattern matches vertical emotion/format fit"]
