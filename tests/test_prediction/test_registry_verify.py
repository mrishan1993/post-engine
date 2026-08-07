from __future__ import annotations

from sqlalchemy import select

from db.models import Prediction, PredictionError, VerificationResult
from db.session import get_session
from prediction.registry import PredictionRegistry
from prediction.verification import verify_prediction
from trend_engine.v2.pipeline import run_v2_intelligence


def test_v2_briefs_create_registry_predictions(db_url: str) -> None:
    with get_session(db_url) as session:
        result = run_v2_intelligence(session, vertical="horror_narration")
        assert result.briefs >= 1
        preds = session.scalars(select(Prediction)).all()
        assert preds
        assert all(p.subsystem == "probability_engine" for p in preds)
        assert all(p.content_brief_id is not None for p in preds)
        assert all(p.reasoning_json for p in preds)
        features = preds[0].features
        assert features
        assert any(f.feature_name == "hook_strength" for f in features)


def test_verify_computes_errors_and_lesson(db_url: str) -> None:
    with get_session(db_url) as session:
        registry = PredictionRegistry(session)
        row, result = registry.predict_and_record(
            opportunity={
                "trend": "POV Horror",
                "emotion": "fear",
                "hook": "I should never have opened that door...",
                "hook_type": "open_loop",
                "story_pattern": "pov",
                "lifecycle": "growing",
                "platforms": ["youtube"],
                "confidence": 0.8,
            },
            score_breakdown={
                "virality": 0.85,
                "novelty": 0.8,
                "growth": 0.8,
                "competition": 0.6,
                "character_fit": 0.8,
                "audience_fit": 0.8,
                "brand_fit": 0.8,
            },
            lifecycle_stage="growing",
            vertical_slug="horror_narration",
            character={"slug": "ghost_kid"},
        )
        # Severe miss
        actual_views = max(int(result.predicted_views * 0.25), 1)
        verification = verify_prediction(
            session,
            row.id,
            {"views": actual_views, "comments": 10, "watch_time_sec": 12, "revenue_usd": 5, "ctr": 0.03},
        )
        assert verification.mape is not None
        assert row.status == "verified"
        errors = session.scalars(
            select(PredictionError).where(PredictionError.prediction_id == row.id)
        ).all()
        assert errors
        assert verification.explanation
        assert "suggested_confidence" in verification.explanation
