from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from db.models import (
    PromptPackage,
    Storyboard,
    VoiceArtifact,
    VoiceGenerationJob,
    VoiceGenerationRequest,
    VoiceProfile,
    VoiceTimelineRow,
)
from voice_generation_engine.executor import VoiceJobExecutor, allocate_voice_variants
from voice_generation_engine.registry import (
    ensure_provider_mappings,
    get_voice_profile,
    list_voice_profiles,
    resolve_character_voice,
)
from voice_generation_engine.router import route_voice_provider, voice_fallback_chain
from voice_generation_engine.schemas import (
    DialogueScript,
    ProviderStrategy,
    VoiceGenerationRequestIn,
    VoiceSpecification,
)
from voice_generation_engine.spec_builder import (
    build_voice_spec_from_text,
    build_voice_specs_from_dialogue,
    extract_dialogue_from_storyboard,
)
from voice_generation_engine.timing import build_voice_timeline, voice_spec_to_provider_request
from voice_generation_engine.providers import get_voice_provider
from voice_generation_engine.registry import provider_voice_id


class VoiceGenerationService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, request: VoiceGenerationRequestIn | dict[str, Any]) -> VoiceGenerationRequest:
        """
        Create one or more voice generation requests.
        Multi-line dialogue → one request per line, then optional timeline.
        """
        req_in = (
            request
            if isinstance(request, VoiceGenerationRequestIn)
            else VoiceGenerationRequestIn.model_validate(request)
        )

        if req_in.idempotency_key:
            existing = self.session.scalar(
                select(VoiceGenerationRequest).where(
                    VoiceGenerationRequest.idempotency_key == req_in.idempotency_key
                )
            )
            if existing:
                return existing

        specs = self._resolve_specs(req_in)
        if not specs:
            raise ValueError("no voice specifications resolved")

        # Generate each line independently (multi-character orchestration)
        requests: list[VoiceGenerationRequest] = []
        for idx, spec in enumerate(specs):
            idem = None
            if req_in.idempotency_key and len(specs) == 1:
                idem = req_in.idempotency_key
            elif req_in.idempotency_key:
                idem = f"{req_in.idempotency_key}:{idx}"
            vreq = self._create_single(
                req_in,
                spec,
                idempotency_key=idem,
                process=req_in.process,
            )
            requests.append(vreq)

        primary = requests[0]
        if req_in.build_timeline and all(r.status == "completed" for r in requests):
            self.create_timeline_from_requests(requests, storyboard_id=req_in.storyboard_id)
        return primary

    def _create_single(
        self,
        req_in: VoiceGenerationRequestIn,
        spec: VoiceSpecification,
        *,
        idempotency_key: str | None,
        process: bool,
    ) -> VoiceGenerationRequest:
        if idempotency_key:
            existing = self.session.scalar(
                select(VoiceGenerationRequest).where(
                    VoiceGenerationRequest.idempotency_key == idempotency_key
                )
            )
            if existing:
                return existing

        profile = None
        if spec.voice_profile_id:
            profile = get_voice_profile(self.session, spec.voice_profile_id)
            if profile:
                ensure_provider_mappings(profile)

        strategy = req_in.provider_strategy
        provider, scores = route_voice_provider(self.session, spec, strategy, profile=profile)

        variant_count = int((req_in.variants or {}).get("count") or 1)
        variant_count = max(1, min(variant_count, 6))
        mapped = provider_voice_id(profile, provider)
        est = get_voice_provider(provider).estimate_cost(
            voice_spec_to_provider_request(spec, provider_voice_id=mapped)
        )
        max_cost = float((req_in.budget or {}).get("max_cost_usd") or 1.0)
        if est * variant_count > max_cost:
            variant_count = max(1, int(max_cost // max(est, 0.001)))

        lineage = {
            **spec.lineage,
            "story_id": req_in.story_id,
            "storyboard_id": req_in.storyboard_id,
            "dialogue_id": spec.dialogue_id,
            "character_id": spec.character_id,
            "voice_profile_id": spec.voice_profile_id,
        }

        vreq = VoiceGenerationRequest(
            id=str(uuid4()),
            content_id=req_in.content_id,
            story_id=req_in.story_id,
            storyboard_id=req_in.storyboard_id,
            character_id=spec.character_id or req_in.character_id,
            voice_profile_id=spec.voice_profile_id or req_in.voice_profile_id,
            prompt_package_id=req_in.prompt_package_id,
            script={"text": spec.text, "dialogue_id": spec.dialogue_id},
            voice_spec=spec.model_dump(),
            provider_strategy=strategy.model_dump(),
            variant_count=variant_count,
            budget=req_in.budget,
            quality=req_in.quality,
            priority=req_in.priority,
            status="queued",
            idempotency_key=idempotency_key,
            lineage=lineage,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(vreq)
        self.session.flush()

        get_bus().publish(
            EventType.VOICE_GENERATION_REQUESTED,
            {
                "request_id": vreq.id,
                "character_id": vreq.character_id,
                "voice_profile_id": vreq.voice_profile_id,
                "variants": variant_count,
                "text_preview": spec.text[:80],
            },
            producer="voice-generation-engine",
        )

        fb = voice_fallback_chain(strategy, provider)
        plan = allocate_voice_variants(
            count=variant_count,
            strategy=str((req_in.variants or {}).get("strategy") or "different_emotion"),
            primary=provider,
            fallbacks=fb,
        )
        jobs = []
        for item in plan:
            job = VoiceGenerationJob(
                id=str(uuid4()),
                request_id=vreq.id,
                variant_number=item["variant_number"],
                provider=item["provider"],
                status="queued",
                seed=item["seed"],
                prompt_package_id=req_in.prompt_package_id,
                estimated_cost=est,
                parameters={
                    "routing_score": scores,
                    "variant_deltas": item.get("variant_deltas"),
                },
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(job)
            jobs.append(job)
        self.session.flush()

        get_bus().publish(
            EventType.VOICE_GENERATION_QUEUED,
            {"request_id": vreq.id, "jobs": [j.id for j in jobs]},
            producer="voice-generation-engine",
        )

        if process:
            VoiceJobExecutor(self.session).process_request(vreq.id)
            self.session.refresh(vreq)
        return vreq

    def create_timeline_from_requests(
        self,
        requests: list[VoiceGenerationRequest],
        *,
        storyboard_id: str | None = None,
    ) -> VoiceTimelineRow:
        items = []
        for req in requests:
            arts = self.list_artifacts(req.id)
            if not arts:
                continue
            # Prefer highest technical score variant
            best = max(
                arts,
                key=lambda a: float((a.technical_qa or {}).get("technical_score") or 0),
            )
            items.append(
                {
                    "spec": req.voice_spec or {},
                    "artifact_id": best.id,
                    "duration_sec": float(best.duration_sec or 0),
                    "request_id": req.id,
                }
            )
        timeline = build_voice_timeline(specs_with_artifacts=items)
        row = VoiceTimelineRow(
            id=str(uuid4()),
            storyboard_id=storyboard_id or (requests[0].storyboard_id if requests else None),
            duration_sec=timeline.duration_sec,
            segments=[s.model_dump() for s in timeline.segments],
            status="ready",
            lineage={"request_ids": [r.id for r in requests]},
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.VOICE_TIMELINE_CREATED,
            {
                "timeline_id": row.id,
                "storyboard_id": row.storyboard_id,
                "segment_count": len(row.segments or []),
                "duration_sec": float(row.duration_sec),
            },
            producer="voice-generation-engine",
        )
        return row

    def process(self, request_id: str) -> VoiceGenerationRequest:
        return VoiceJobExecutor(self.session).process_request(request_id)

    def get_request(self, request_id: str) -> VoiceGenerationRequest | None:
        return self.session.get(VoiceGenerationRequest, request_id)

    def list_jobs(self, request_id: str) -> list[VoiceGenerationJob]:
        return list(
            self.session.scalars(
                select(VoiceGenerationJob)
                .where(VoiceGenerationJob.request_id == request_id)
                .order_by(VoiceGenerationJob.variant_number)
            ).all()
        )

    def list_artifacts(self, request_id: str) -> list[VoiceArtifact]:
        jobs = self.list_jobs(request_id)
        if not jobs:
            return []
        return list(
            self.session.scalars(
                select(VoiceArtifact).where(
                    VoiceArtifact.generation_job_id.in_([j.id for j in jobs])
                )
            ).all()
        )

    def get_timeline(self, timeline_id: str) -> VoiceTimelineRow | None:
        row = self.session.get(VoiceTimelineRow, timeline_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(VoiceTimelineRow).where(VoiceTimelineRow.id.startswith(timeline_id))
            ).all()
        )
        return rows[0] if len(rows) == 1 else None

    def list_profiles(self) -> list[VoiceProfile]:
        return list_voice_profiles(self.session)

    def get_character_voice(self, character_id_or_slug: str) -> dict[str, Any]:
        char, profile = resolve_character_voice(
            self.session, character_id=character_id_or_slug
        )
        if not char:
            char, profile = resolve_character_voice(
                self.session, character_slug=character_id_or_slug
            )
        if not char:
            raise ValueError("character not found")
        return {
            "character_id": char.id,
            "character_slug": char.slug,
            "voice_profile_id": profile.id if profile else None,
            "voice_profile_slug": profile.slug if profile else None,
            "provider_mappings": (profile.provider_mappings if profile else None),
            "characteristics": (profile.characteristics if profile else None),
        }

    def regenerate(self, request_id: str) -> VoiceGenerationRequest:
        old = self.get_request(request_id)
        if not old:
            raise ValueError("request not found")
        return self.create(
            VoiceGenerationRequestIn(
                story_id=old.story_id,
                storyboard_id=old.storyboard_id,
                character_id=old.character_id,
                voice_profile_id=old.voice_profile_id,
                prompt_package_id=old.prompt_package_id,
                voice_spec=old.voice_spec,
                provider_strategy=ProviderStrategy.model_validate(old.provider_strategy or {}),
                variants={"count": old.variant_count, "strategy": "different_emotion"},
                budget=old.budget or {},
                quality=old.quality or {},
                priority=old.priority,  # type: ignore[arg-type]
                process=True,
                build_timeline=False,
            )
        )

    def _resolve_specs(self, req_in: VoiceGenerationRequestIn) -> list[VoiceSpecification]:
        if req_in.voice_spec:
            spec = (
                req_in.voice_spec
                if isinstance(req_in.voice_spec, VoiceSpecification)
                else VoiceSpecification.model_validate(req_in.voice_spec)
            )
            return [self._enrich_spec(spec, req_in)]

        if req_in.dialogue:
            if isinstance(req_in.dialogue, list):
                dialogue = DialogueScript.model_validate({"lines": req_in.dialogue})
            elif isinstance(req_in.dialogue, DialogueScript):
                dialogue = req_in.dialogue
            else:
                dialogue = DialogueScript.model_validate(req_in.dialogue)
            return [
                self._enrich_spec(s, req_in)
                for s in build_voice_specs_from_dialogue(self.session, dialogue)
            ]

        if req_in.storyboard_id:
            board = self.session.get(Storyboard, req_in.storyboard_id)
            if not board:
                rows = list(
                    self.session.scalars(
                        select(Storyboard).where(Storyboard.id.startswith(req_in.storyboard_id))
                    ).all()
                )
                if len(rows) != 1:
                    raise ValueError("storyboard not found")
                board = rows[0]
            dialogue = extract_dialogue_from_storyboard(board.document or {})
            if not dialogue.lines:
                # Fallback: invent nothing — use a hook caption if present as narration only if text exists
                raise ValueError(
                    "storyboard has no narration/dialogue text for voice generation"
                )
            specs = build_voice_specs_from_dialogue(self.session, dialogue)
            return [self._enrich_spec(s, req_in) for s in specs]

        if req_in.prompt_package_id:
            pkg = self.session.get(PromptPackage, req_in.prompt_package_id)
            if not pkg:
                raise ValueError("prompt package not found")
            params = (pkg.provider_prompt or {}).get("parameters") or {}
            text = str(params.get("text") or (pkg.provider_prompt or {}).get("positive_prompt") or "")
            if not text:
                raise ValueError("prompt package has no voice text")
            spec = build_voice_spec_from_text(
                text=text,
                character_id=req_in.character_id,
                character_slug=req_in.character_slug,
                voice_profile_id=req_in.voice_profile_id or params.get("voice_profile_id"),
                emotion=str(params.get("emotion") or "neutral"),
                intensity=float(params.get("intensity") or 0.7),
            )
            return [self._enrich_spec(spec, req_in)]

        if req_in.character_slug or req_in.character_id:
            raise ValueError("provide dialogue, storyboard_id, voice_spec, or prompt_package_id")

        raise ValueError(
            "storyboard_id, dialogue, voice_spec, or prompt_package_id required"
        )

    def _enrich_spec(
        self, spec: VoiceSpecification, req_in: VoiceGenerationRequestIn
    ) -> VoiceSpecification:
        if not spec.voice_profile_id or not spec.character_id:
            char, profile = resolve_character_voice(
                self.session,
                character_id=spec.character_id or req_in.character_id,
                character_slug=spec.character_slug or req_in.character_slug,
            )
            updates: dict[str, Any] = {}
            if char and not spec.character_id:
                updates["character_id"] = char.id
                updates["character_slug"] = char.slug
            if profile and not spec.voice_profile_id:
                updates["voice_profile_id"] = profile.id
            if updates:
                spec = spec.model_copy(update=updates)
        if req_in.voice_profile_id and not spec.voice_profile_id:
            spec = spec.model_copy(update={"voice_profile_id": req_in.voice_profile_id})
        return spec


def create_voice_generation(
    session: Session, request: VoiceGenerationRequestIn | dict[str, Any]
) -> VoiceGenerationRequest:
    return VoiceGenerationService(session).create(request)
