from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from amp_platform.events.types import TrendOpportunityCreated
from config.loader import load_vertical_config
from config.settings import Settings, get_settings
from db.models import ContentBrief, ContentFeature, OpportunityScore, RawContent
from orchestration.pipeline import Pipeline
from trend_engine.collectors.google_trends_collector import GoogleTrendsCollector
from trend_engine.collectors.youtube_collector import YouTubeCollector
from trend_engine.processing.normalizer import persist_signals
from trend_engine.scheduler.daily_run import load_sources_config
from trend_engine.v2.briefs import generate_opportunity_briefs
from trend_engine.v2.discovery import ingest_raw_content
from trend_engine.v2.features.extractor import extract_content_dna
from trend_engine.v2.graph import build_graph_from_features
from trend_engine.v2.opportunity import persist_opportunities, rank_opportunities
from trend_engine.v2.patterns.lifecycle import update_lifecycles

V2_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "v2.yaml"


@dataclass
class V2RunResult:
    raw_content: int = 0
    features: int = 0
    opportunities: int = 0
    briefs: int = 0
    graph_edges: int = 0
    opportunity_rows: list[OpportunityScore] = field(default_factory=list)
    briefs_created: list[ContentBrief] = field(default_factory=list)


def load_v2_config(path: Path | None = None) -> dict[str, Any]:
    with (path or V2_CONFIG_PATH).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def run_v2_intelligence(
    session: Session,
    *,
    vertical: str | None = None,
    settings: Settings | None = None,
    sources_config: dict[str, Any] | None = None,
    v2_config: dict[str, Any] | None = None,
) -> V2RunResult:
    """
    Full V2 path:
    collect → raw_content → Content DNA → lifecycle/graph →
    opportunity rank → character adaptation → content_briefs
    """
    settings = settings or get_settings()
    src_cfg = sources_config or load_sources_config()
    cfg = v2_config or load_v2_config()
    stub = bool(src_cfg.get("stub_mode", True) or settings.trend_stub_collectors)

    pipeline = Pipeline(session, settings=settings)
    vertical_cfgs = cfg.get("verticals") or {}
    target_verticals = [vertical] if vertical else list(vertical_cfgs.keys())
    for slug in target_verticals:
        try:
            load_vertical_config(slug)
            pipeline.ensure_vertical(slug)
        except FileNotFoundError:
            continue

    raw_signals = []
    yt_cfg = src_cfg.get("youtube", {})
    if yt_cfg.get("enabled", True):
        raw_signals.extend(
            YouTubeCollector(
                api_key=settings.youtube_api_key,
                regions=yt_cfg.get("regions"),
                category_ids=yt_cfg.get("category_ids"),
                max_results=int(yt_cfg.get("max_results_per_query", 15)),
                stub=stub,
            ).collect()
        )
    gt_cfg = src_cfg.get("google_trends", {})
    if gt_cfg.get("enabled", True):
        raw_signals.extend(
            GoogleTrendsCollector(
                seed_queries=gt_cfg.get("seed_queries"),
                geo=gt_cfg.get("geo", ""),
                timeframe=gt_cfg.get("timeframe", "now 7-d"),
                stub=stub,
            ).collect()
        )

    signals = persist_signals(session, raw_signals)
    raw_items = ingest_raw_content(session, signals)
    features = extract_content_dna(
        session, raw_items, lexicon=cfg.get("pattern_lexicon")
    )
    pairs = list(zip(raw_items, features, strict=True))
    update_lifecycles(session, pairs)

    result = V2RunResult(raw_content=len(raw_items), features=len(features))
    all_briefs: list[ContentBrief] = []
    all_opps: list[OpportunityScore] = []
    edges = 0

    for slug in target_verticals:
        vcfg = vertical_cfgs.get(slug) or {}
        characters = _load_characters(session, slug, cfg)
        # Filter pairs that fit vertical emotion/audience loosely
        relevant = _filter_for_vertical(pairs, slug, vcfg)
        edges += build_graph_from_features(session, relevant, vertical_slug=slug)
        ranked = rank_opportunities(
            session,
            relevant,
            vertical_slug=slug,
            vertical_cfg=vcfg,
            characters=characters,
            weights=cfg.get("opportunity_weights"),
            reject_stages=cfg.get("reject_lifecycle_stages"),
            min_score=float(cfg.get("min_opportunity_score", 55)),
            max_results=int(cfg.get("max_opportunities_per_vertical", 5)),
        )
        opp_rows = persist_opportunities(session, ranked)
        for row, ranked_opp in zip(opp_rows, ranked, strict=True):
            get_bus().publish(
                EventType.TREND_OPPORTUNITY_CREATED,
                TrendOpportunityCreated(
                    opportunity_id=row.id,
                    vertical_slug=row.vertical_slug,
                    score=float(row.score),
                    lifecycle=row.lifecycle_stage,
                    pattern_key=row.pattern_key,
                    title=row.title,
                    dna_summary={
                        "emotion": (ranked_opp.payload or {}).get("emotion"),
                        "story_pattern": (ranked_opp.payload or {}).get("story_pattern"),
                        "hook_type": (ranked_opp.payload or {}).get("hook_type"),
                    },
                ),
                producer="trend-service",
            )
            briefs = generate_opportunity_briefs(
                session,
                row,
                ranked_opp,
                characters=characters,
                briefs_per_opportunity=int(cfg.get("briefs_per_opportunity", 3)),
            )
            all_briefs.extend(briefs)
        all_opps.extend(opp_rows)

    result.opportunities = len(all_opps)
    result.briefs = len(all_briefs)
    result.graph_edges = edges
    result.opportunity_rows = all_opps
    result.briefs_created = all_briefs
    return result


def _load_characters(session, vertical_slug: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer Asset Engine characters; fall back to v2.yaml stubs."""
    try:
        from asset_engine.characters import CharacterRegistry

        reg = CharacterRegistry(session)
        rows = [
            reg.to_adaptation_dict(c)
            for c in reg.list_characters(status="active")
            if vertical_slug in (c.tags or [])
        ]
        if rows:
            return rows
    except Exception:  # noqa: BLE001
        pass
    return list((cfg.get("characters") or {}).get(vertical_slug) or [])


def _filter_for_vertical(
    pairs: list[tuple[RawContent, ContentFeature]],
    slug: str,
    vcfg: dict[str, Any],
) -> list[tuple[RawContent, ContentFeature]]:
    preferred = set(vcfg.get("emotions_preferred") or [])
    audience = vcfg.get("audience")
    matched = []
    for raw, feat in pairs:
        dominant = (feat.emotion or {}).get("dominant")
        if preferred and dominant in preferred:
            matched.append((raw, feat))
        elif audience and feat.audience == audience:
            matched.append((raw, feat))
        elif slug.replace("_", " ") in (raw.title or "").lower():
            matched.append((raw, feat))
    # Fall back to all if filter too aggressive for stub data
    return matched or pairs


def answer_what_to_make(
    session: Session, vertical: str, *, limit: int = 5
) -> list[OpportunityScore]:
    """'If we publish in the next 12 hours, what should we make?'"""
    return list(
        session.scalars(
            select(OpportunityScore)
            .where(
                OpportunityScore.vertical_slug == vertical,
                OpportunityScore.status == "active",
            )
            .order_by(OpportunityScore.score.desc())
            .limit(limit)
        ).all()
    )
