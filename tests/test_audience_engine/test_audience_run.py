from __future__ import annotations

from amp_platform.events import EventType, get_bus, reset_bus
from audience_engine.nlp import analyze_comment, detect_language, is_spam_or_noise
from audience_engine.schemas import (
    AcceptOpportunityRequest,
    AnalyticsIn,
    CommentIn,
    CreateSegmentRequest,
    IngestBatchRequest,
)
from audience_engine.service import AudienceService
from campaign_engine.schemas import CreateCampaignRequest
from campaign_engine.service import CampaignService
from db.session import get_session
from strategy_engine.schemas import CreateStrategyRequest, StrategyProfile
from strategy_engine.service import StrategyService


def test_nlp_multilingual_and_noise() -> None:
    assert detect_language("bhai ye character wapas lao 😂") == "hinglish"
    assert detect_language("This is great") == "en"
    noise, reason = is_spam_or_noise("Check my bio for free followers http://x.com")
    assert noise and reason == "spam_pattern"
    seen: set[str] = set()
    a1 = analyze_comment("Bring Character B back", characters=["character_a", "character_b"], seen_normalized=seen)
    seen.add(a1["text_normalized"])
    a2 = analyze_comment("Bring Character B back", characters=["character_a", "character_b"], seen_normalized=seen)
    assert a1["intent_type"] == "character_request"
    assert a2["is_noise"]  # duplicate
    hi = analyze_comment(
        "bhai ye character wapas lao 😂",
        characters=["character_a", "character_b"],
    )
    assert hi["language"] == "hinglish"
    assert hi["intent_type"] == "character_request"


def test_audience_end_to_end(db_url: str) -> None:
    reset_bus()
    bus = get_bus()
    with get_session(db_url) as session:
        strategy = StrategyService(session).create_strategy(
            CreateStrategyRequest(
                name="growth",
                character_slug="ghost_kid",
                profile=StrategyProfile(),
            )
        )
        campaign = CampaignService(session).create_campaign(
            CreateCampaignRequest(
                name="Meet Cast",
                character_slug="ghost_kid",
                strategy_id=strategy.strategy_id,
                episode_count=4,
                auto_decompose=True,
            )
        )
        svc = AudienceService(session)
        svc.create_segment(
            CreateSegmentRequest(
                name="high_engagement_character_fans",
                segment_kind="discovered",
                criteria={"watches_gt": 0.8, "comments_frequently": True},
                size=1200,
                lifecycle_stage="fan",
            )
        )

        comments = []
        # Demand: A + B pairing (volume >= 5)
        for text in [
            "Character A + Character B please",
            "Make Character A meet Character B",
            "A + B together would be amazing",
            "Character A and Character B forever",
            "We need Character A + Character B",
            "Pairing Character A + Character B",
            "Bring Character B back",
            "Where is Character B?",
            "WE WANT B",
            "bhai ye character wapas lao 😂",
            "Bring Character B back now",
            "Need longer episodes",
            "Please make longer episodes",
            "Longer episodes please",
            "We need longer episodes",
            "Make longer episodes",
            "This is the funniest thing I've seen",
            "How does this work?",
            "Check my bio for free followers http://spam.test",
            "Check my bio for free followers http://spam.test",
            "first",
        ]:
            comments.append(
                CommentIn(
                    text=text,
                    content_id="reel_1",
                    user_tier="fan",
                    likes=10,
                )
            )

        overview = svc.ingest(
            IngestBatchRequest(
                comments=comments,
                analytics=[
                    AnalyticsIn(
                        content_id="reel_1",
                        views=1_800_000,
                        likes=92_000,
                        shares=14_000,
                        comments=8000,
                        follows=5000,
                        unfollows=100,
                        returning_viewer_rate=0.6,
                        completion_rate=0.72,
                    )
                ],
                characters=["character_a", "character_b"],
                content_id="reel_1",
                process=True,
            )
        )

        assert overview.noise_filtered >= 2
        assert overview.topics
        assert overview.demands
        assert overview.opportunities
        assert overview.character_affinity
        assert overview.community_health > 0
        # Evidence / confidence on demand
        top = overview.demands[0]
        assert top.confidence and top.confidence >= 0.7
        assert top.evidence.get("evidence_count") or top.volume >= 5

        # AC10 strategy integration
        opp = overview.opportunities[0]
        accepted = svc.accept_opportunity(
            AcceptOpportunityRequest(
                opportunity_id=opp.opportunity_id,
                strategy_id=strategy.strategy_id,
                campaign_id=campaign.campaign_id,
                series_id=campaign.series[0].series_id,
                push_to_strategy=True,
                push_to_campaign=True,
            )
        )
        assert accepted.status == "acted_upon"
        assert accepted.strategy_opportunity_id
        assert accepted.campaign_episode_id

        # Alerts exist (health / spam etc. depending on mix)
        refreshed = svc.overview()
        assert refreshed.interaction_count >= len(comments)

        seen = {e.event_type for e in bus.history}
        assert EventType.AUDIENCE_SIGNAL_DETECTED in seen
        assert EventType.AUDIENCE_INTENT_DETECTED in seen
        assert EventType.AUDIENCE_DEMAND_DETECTED in seen
        assert EventType.CONTENT_OPPORTUNITY_CREATED in seen
        assert EventType.COMMUNITY_TOPIC_DETECTED in seen
        assert EventType.CHARACTER_AFFINITY_CHANGED in seen
