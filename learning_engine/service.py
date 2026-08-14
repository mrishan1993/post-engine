from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from learning_engine.dataset import ingest_verification, list_observations, seed_observation
from learning_engine.experiments import (
    assign_variant,
    complete_experiment,
    create_experiment,
    get_experiment,
    list_experiments,
)
from learning_engine.model_registry import (
    compare_models,
    list_models,
    promote_model,
    train_challenger,
)
from learning_engine.optimizer import generate_profile, get_active_profile
from learning_engine.patterns import analyze_patterns, character_profile, trend_conversion
from learning_engine.policy import DEFAULT_POLICY
from learning_engine.schemas import (
    CreateExperimentRequest,
    CreateObservationRequest,
    IngestVerificationRequest,
    OptimizationProfileOut,
    PromoteModelRequest,
    RecommendRequest,
    ScopeSpec,
    TrainModelRequest,
)


class LearningService:
    """Learning & Optimization Engine — evidence → recommendations → briefs.

    Does not generate content or mutate production models in place.
    Autonomy levels 1–2 in V1 (analyze + recommend).
    """

    def __init__(self, session: Session):
        self.session = session

    def ingest_verification(
        self, request: IngestVerificationRequest | dict[str, Any] | str
    ) -> dict[str, Any] | None:
        if isinstance(request, str):
            vid = request
        elif isinstance(request, IngestVerificationRequest):
            vid = request.verification_id
        else:
            vid = IngestVerificationRequest.model_validate(request).verification_id
        obs = ingest_verification(self.session, vid)
        if not obs:
            return None
        return {
            "observation_id": obs.id,
            "excluded": obs.excluded,
            "exclude_reason": obs.exclude_reason,
            "confidence": float(obs.confidence or 0),
            "feature_vector": obs.feature_vector,
            "outcome_vector": obs.outcome_vector,
        }

    def add_observation(self, request: CreateObservationRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, CreateObservationRequest)
            else CreateObservationRequest.model_validate(request)
        )
        if req.verification_id:
            out = self.ingest_verification(req.verification_id)
            if out:
                return out
        obs = seed_observation(
            self.session,
            feature_vector=req.feature_vector,
            outcome_vector=req.outcome_vector,
            confidence=req.confidence or 0.8,
        )
        return {
            "observation_id": obs.id,
            "excluded": obs.excluded,
            "feature_vector": obs.feature_vector,
            "outcome_vector": obs.outcome_vector,
        }

    def list_learning(
        self,
        *,
        character: str | None = None,
        platform: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = list_observations(
            self.session, character=character, platform=platform, limit=limit
        )
        return [
            {
                "id": r.id,
                "content_id": r.content_id,
                "publication_id": r.publication_id,
                "prediction_ref": r.prediction_ref,
                "source_verification_id": r.source_verification_id,
                "feature_vector": r.feature_vector,
                "outcome_vector": r.outcome_vector,
                "confidence": float(r.confidence or 0),
                "excluded": r.excluded,
                "quality_flags": r.quality_flags,
            }
            for r in rows
        ]

    def patterns(
        self,
        *,
        character: str | None = None,
        platform: str | None = None,
        metric: str = "completion_rate",
    ) -> list[dict[str, Any]]:
        obs = list_observations(self.session, character=character, platform=platform)
        scope = ScopeSpec(character=character, platform=platform)
        return [p.model_dump() for p in analyze_patterns(obs, scope=scope, metric=metric)]

    def recommend(
        self, request: RecommendRequest | dict[str, Any] | None = None
    ) -> OptimizationProfileOut:
        req = (
            RecommendRequest()
            if request is None
            else request
            if isinstance(request, RecommendRequest)
            else RecommendRequest.model_validate(request)
        )
        obs = list_observations(
            self.session,
            character=req.scope.character,
            platform=req.scope.platform,
            limit=2000,
        )
        return generate_profile(self.session, obs, req)

    def get_profile(
        self,
        *,
        character: str | None = None,
        platform: str | None = None,
    ) -> OptimizationProfileOut | None:
        return get_active_profile(self.session, character=character, platform=platform)

    def brief(
        self,
        *,
        character: str | None = None,
        platform: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Primary V1 output: Content Optimization Brief for the next post."""
        profile = self.recommend(
            RecommendRequest(
                scope=ScopeSpec(character=character, platform=platform),
                persist=persist,
                include_exploration=True,
            )
        )
        return {
            "profile_id": profile.profile_id,
            "brief": profile.brief.model_dump() if profile.brief else None,
            "confidence": profile.confidence,
            "observation_count": profile.observation_count,
            "recommendations": [r.model_dump() for r in profile.recommendations],
            "autonomy_level": profile.policy.autonomy_level,
            "note": "Story Engine owns narrative; this brief only constrains choices",
        }

    def character(self, character_id: str) -> dict[str, Any]:
        obs = list_observations(self.session, character=character_id, limit=2000)
        return character_profile(obs, character_id)

    def trends(self) -> list[dict[str, Any]]:
        obs = list_observations(self.session, limit=2000)
        return trend_conversion(obs)

    def create_experiment(
        self, request: CreateExperimentRequest | dict[str, Any]
    ) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, CreateExperimentRequest)
            else CreateExperimentRequest.model_validate(request)
        )
        exp = create_experiment(self.session, req)
        return _exp_out(exp)

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        return _exp_out(get_experiment(self.session, experiment_id))

    def assign_experiment(self, experiment_id: str) -> dict[str, Any]:
        return assign_variant(self.session, experiment_id)

    def complete_experiment(
        self, experiment_id: str, results: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return _exp_out(complete_experiment(self.session, experiment_id, results))

    def list_experiments(self, *, status: str | None = None) -> list[dict[str, Any]]:
        return [_exp_out(e) for e in list_experiments(self.session, status=status)]

    def train_model(self, request: TrainModelRequest | dict[str, Any] | None = None) -> dict[str, Any]:
        req = (
            TrainModelRequest()
            if request is None
            else request
            if isinstance(request, TrainModelRequest)
            else TrainModelRequest.model_validate(request)
        )
        row = train_challenger(self.session, req)
        return {
            "id": row.id,
            "model_name": row.model_name,
            "version": row.version,
            "status": row.status,
            "metrics": row.metrics,
            "weights": row.weights,
        }

    def compare_models(self, model_a: str, model_b: str) -> dict[str, Any]:
        return compare_models(self.session, model_a, model_b)

    def promote_model(self, request: PromoteModelRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request
            if isinstance(request, PromoteModelRequest)
            else PromoteModelRequest.model_validate(request)
        )
        row = promote_model(self.session, req)
        return {
            "id": row.id,
            "model_name": row.model_name,
            "version": row.version,
            "status": row.status,
            "promoted_at": row.promoted_at.isoformat() if row.promoted_at else None,
        }

    def list_models(self, *, model_name: str | None = None) -> list[dict[str, Any]]:
        return list_models(self.session, model_name=model_name)

    def from_verification_hook(self, verification_id: str) -> dict[str, Any] | None:
        """Soft entrypoint after Verification — never raises to caller."""
        try:
            return self.ingest_verification(verification_id)
        except Exception:  # noqa: BLE001
            return None

    def policy_defaults(self) -> dict[str, Any]:
        return DEFAULT_POLICY.model_dump()


def _exp_out(exp: Any) -> dict[str, Any]:
    return {
        "id": exp.id,
        "hypothesis": exp.hypothesis,
        "variable": exp.variable,
        "control": exp.control,
        "variants": exp.variants,
        "target_metric": exp.target_metric,
        "status": exp.status,
        "sample_target": exp.sample_target,
        "sample_count": exp.sample_count,
        "assignment_counts": exp.assignment_counts,
        "results": exp.results,
        "scope": exp.scope,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
        "completed_at": exp.completed_at.isoformat() if exp.completed_at else None,
    }
