from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from config.loader import load_vertical_config
from config.settings import Settings, get_settings
from db.models import ContentBrief, TrendTopic
from orchestration.pipeline import Pipeline
from trend_engine.brief_generator.generator import generate_briefs
from trend_engine.collectors.google_trends_collector import GoogleTrendsCollector
from trend_engine.collectors.youtube_collector import YouTubeCollector
from trend_engine.processing.normalizer import persist_signals
from trend_engine.processing.scoring_agent import score_topics
from trend_engine.processing.topic_clustering_agent import assign_one_to_one_topics

SOURCES_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"


@dataclass
class DailyRunResult:
    signals_collected: int = 0
    topics_created: int = 0
    briefs_created: int = 0
    briefs: list[ContentBrief] = field(default_factory=list)
    per_vertical_candidates: dict[str, int] = field(default_factory=dict)


def load_sources_config(path: Path | None = None) -> dict[str, Any]:
    with (path or SOURCES_PATH).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def run_daily_ingestion(
    session: Session,
    *,
    settings: Settings | None = None,
    sources_config: dict[str, Any] | None = None,
) -> DailyRunResult:
    settings = settings or get_settings()
    cfg = sources_config or load_sources_config()
    stub = bool(cfg.get("stub_mode", True) or settings.trend_stub_collectors)

    # Ensure verticals exist so brief generator can FK them
    pipeline = Pipeline(session, settings=settings)
    routing = cfg.get("vertical_routing", {})
    for slug in routing:
        try:
            load_vertical_config(slug)
            pipeline.ensure_vertical(slug)
        except FileNotFoundError:
            continue

    raw = []
    yt_cfg = cfg.get("youtube", {})
    if yt_cfg.get("enabled", True):
        yt = YouTubeCollector(
            api_key=settings.youtube_api_key,
            regions=yt_cfg.get("regions"),
            category_ids=yt_cfg.get("category_ids"),
            max_results=int(yt_cfg.get("max_results_per_query", 15)),
            stub=stub,
        )
        raw.extend(yt.collect())

    gt_cfg = cfg.get("google_trends", {})
    if gt_cfg.get("enabled", True):
        gt = GoogleTrendsCollector(
            seed_queries=gt_cfg.get("seed_queries"),
            geo=gt_cfg.get("geo", ""),
            timeframe=gt_cfg.get("timeframe", "now 7-d"),
            stub=stub,
        )
        raw.extend(gt.collect())

    signals = persist_signals(session, raw)
    topics = assign_one_to_one_topics(session, signals, vertical_routing=routing)
    score_topics(session, topics, weights=cfg.get("scoring_weights"))
    briefs = generate_briefs(
        session,
        topics,
        min_score=float(cfg.get("brief_min_score", 0.55)),
        max_briefs=int(cfg.get("max_briefs_per_run", 10)),
    )

    per_vertical: dict[str, int] = {}
    for topic in topics:
        for slug in topic.candidate_verticals or []:
            per_vertical[slug] = per_vertical.get(slug, 0) + 1

    return DailyRunResult(
        signals_collected=len(signals),
        topics_created=len(topics),
        briefs_created=len(briefs),
        briefs=briefs,
        per_vertical_candidates=per_vertical,
    )


def count_active_topics_by_vertical(session: Session) -> dict[str, int]:
    topics = session.query(TrendTopic).filter(TrendTopic.status.in_(["active", "briefed"])).all()
    counts: dict[str, int] = {}
    for topic in topics:
        for slug in topic.candidate_verticals or []:
            counts[slug] = counts.get(slug, 0) + 1
    return counts
