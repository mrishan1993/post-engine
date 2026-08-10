from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from asset_engine.characters import CharacterRegistry
from db.models import (
    PromptComponent,
    PromptExperiment,
    PromptPackage,
    PromptSpec,
    Storyboard,
    StoryboardScene,
    StoryboardShot,
)
from prompt_engine.compiler import compile_from_request, compile_package
from prompt_engine.components import COMPONENT_LIBRARY
from prompt_engine.critic import enrich_package
from prompt_engine.registry import rank_providers
from prompt_engine.schemas import CompileRequest, PromptPackageDoc


class PromptService:
    def __init__(self, session: Session):
        self.session = session

    def ensure_components(self) -> int:
        created = 0
        for name, meta in COMPONENT_LIBRARY.items():
            exists = self.session.scalar(
                select(PromptComponent).where(PromptComponent.name == name)
            )
            if exists:
                continue
            self.session.add(
                PromptComponent(
                    id=str(uuid4()),
                    component_type=str(meta["type"]),
                    name=name,
                    content={"text": meta["text"]},
                    version=1,
                    performance_metadata={},
                )
            )
            created += 1
        self.session.flush()
        return created

    def compile(self, request: CompileRequest | dict[str, Any]) -> list[PromptPackage]:
        req = (
            request
            if isinstance(request, CompileRequest)
            else CompileRequest.model_validate(request)
        )
        self.ensure_components()

        shots_payload = self._resolve_shots(req)
        packages: list[PromptPackage] = []

        for item in shots_payload:
            shot = item["shot"]
            scene = item.get("scene")
            gd = item.get("global_direction")
            board = item.get("storyboard")
            char_ctx, resolved = self._resolve_context(board, shot, scene)

            lineage = {
                "storyboard_id": board.id if board else req.storyboard_id,
                "story_id": (board.story_id if board else req.story_id),
                "storyboard_shot_id": shot.get("id") or req.storyboard_shot_id,
                "scene_id": (scene or {}).get("id"),
            }

            if req.experiment:
                packages.extend(
                    self._compile_experiment(req, shot, scene, gd, char_ctx, resolved, lineage)
                )
                continue

            spec, package, provider = compile_from_request(
                req,
                shot=shot,
                scene=scene,
                global_direction=gd,
                character_context=char_ctx,
                resolved_assets=resolved,
                lineage=lineage,
            )
            package = enrich_package(spec, package, provider=provider)
            packages.append(self._persist(spec, package, lineage, provider))

            # Fallback recompile if validation failed hard
            if package.validation and not package.validation.ok and req.fallback_providers:
                for fb in req.fallback_providers:
                    if fb == provider:
                        continue
                    _, fb_pkg = compile_package(spec, provider=fb)
                    fb_pkg = enrich_package(spec, fb_pkg, provider=fb)
                    if fb_pkg.validation and fb_pkg.validation.ok:
                        packages.append(self._persist(spec, fb_pkg, lineage, fb, version=2))
                        break

        return packages

    def compile_storyboard(
        self, storyboard_id: str, *, provider: str | None = None, modality: str = "video"
    ) -> list[PromptPackage]:
        return self.compile(
            CompileRequest(
                storyboard_id=storyboard_id,
                provider=provider,
                modality=modality,  # type: ignore[arg-type]
                compile_all_shots=True,
            )
        )

    def get_package(self, package_id: str) -> PromptPackage | None:
        return self.session.get(PromptPackage, package_id)

    def compare(self, package_ids: list[str]) -> list[PromptPackage]:
        rows = list(
            self.session.scalars(
                select(PromptPackage).where(PromptPackage.id.in_(package_ids))
            ).all()
        )
        rows.sort(key=lambda p: float(p.quality_score or 0), reverse=True)
        return rows

    def rank_providers_for_shot(self, shot: dict[str, Any], modality: str = "video") -> list[dict]:
        needs = {
            "preserve_character_identity": True,
            "camera_motion": ((shot.get("camera") or {}).get("movement") or "static") != "static",
            "duration_sec": shot.get("duration_sec") or 4,
        }
        return [{"provider": n, "score": s} for n, s in rank_providers(modality, needs=needs)]

    def _compile_experiment(
        self,
        req: CompileRequest,
        shot: dict[str, Any],
        scene: dict[str, Any] | None,
        gd: dict[str, Any] | None,
        char_ctx: dict[str, Any],
        resolved: dict[str, Any],
        lineage: dict[str, Any],
    ) -> list[PromptPackage]:
        candidates = [p for p, _ in rank_providers(req.modality, needs={"duration_sec": shot.get("duration_sec") or 4})][:2]
        if req.provider and req.provider not in candidates:
            candidates = [req.provider, *candidates][:2]
        variant_ids: list[str] = []
        packages: list[PromptPackage] = []
        for prov in candidates:
            local = req.model_copy(update={"provider": prov, "experiment": False})
            spec, package, provider = compile_from_request(
                local,
                shot=shot,
                scene=scene,
                global_direction=gd,
                character_context=char_ctx,
                resolved_assets=resolved,
                lineage=lineage,
            )
            package = enrich_package(spec, package, provider=provider)
            row = self._persist(spec, package, lineage, provider)
            packages.append(row)
            variant_ids.append(row.id)

        winner = max(packages, key=lambda p: float(p.quality_score or 0))
        exp = PromptExperiment(
            id=str(uuid4()),
            storyboard_shot_id=str(shot.get("id") or lineage.get("storyboard_shot_id")),
            variants={"package_ids": variant_ids, "providers": candidates},
            selected_variant=winner.id,
            results={
                "winner": winner.id,
                "scores": {p.id: float(p.quality_score or 0) for p in packages},
            },
        )
        self.session.add(exp)
        self.session.flush()
        return packages

    def _persist(
        self,
        spec: Any,
        package: PromptPackageDoc,
        lineage: dict[str, Any],
        provider: str,
        *,
        version: int = 1,
    ) -> PromptPackage:
        spec_id = str(uuid4())
        self.session.add(
            PromptSpec(
                id=spec_id,
                modality=spec.modality,
                canonical_spec=spec.model_dump(),
                version=version,
                storyboard_id=lineage.get("storyboard_id"),
                storyboard_shot_id=lineage.get("storyboard_shot_id"),
                story_id=lineage.get("story_id"),
            )
        )
        self.session.flush()
        package.canonical_spec_id = spec_id
        package.prompt_version = version

        row = PromptPackage(
            id=str(uuid4()),
            prompt_spec_id=spec_id,
            provider=provider,
            model=package.model,
            modality=package.modality,
            provider_prompt=package.model_dump(),
            version=version,
            quality_score=(package.quality.overall if package.quality else None),
            estimated_cost=(package.estimate or {}).get("estimated_cost"),
            estimated_latency_sec=(package.estimate or {}).get("estimated_latency_sec"),
            validation_result=(package.validation.model_dump() if package.validation else None),
            critic_result=(package.critic.model_dump() if package.critic else None),
            lineage=lineage,
            status="validated" if package.validation and package.validation.ok else "compiled",
        )
        self.session.add(row)
        self.session.flush()

        get_bus().publish(
            EventType.PROMPT_PACK_CREATED,
            {
                "prompt_package_id": row.id,
                "prompt_spec_id": spec_id,
                "provider": provider,
                "model": package.model,
                "modality": package.modality,
                "quality_score": float(row.quality_score or 0),
                "storyboard_id": lineage.get("storyboard_id"),
                "storyboard_shot_id": lineage.get("storyboard_shot_id"),
                "story_id": lineage.get("story_id"),
            },
            producer="prompt-engine",
        )
        return row

    def _resolve_shots(self, req: CompileRequest) -> list[dict[str, Any]]:
        if req.shot:
            return [
                {
                    "shot": req.shot,
                    "scene": req.scene,
                    "global_direction": req.global_direction,
                    "storyboard": None,
                }
            ]

        if not req.storyboard_id and not req.storyboard_shot_id:
            raise ValueError("storyboard_id, storyboard_shot_id, or shot payload required")

        board = None
        if req.storyboard_id:
            board = self.session.get(Storyboard, req.storyboard_id)
            if not board:
                rows = list(
                    self.session.scalars(
                        select(Storyboard).where(Storyboard.id.startswith(req.storyboard_id))
                    ).all()
                )
                if len(rows) != 1:
                    raise ValueError("storyboard not found")
                board = rows[0]

        if req.storyboard_shot_id:
            shot_row = self.session.get(StoryboardShot, req.storyboard_shot_id)
            if not shot_row:
                # search by prefix / document
                shot_row = self.session.scalar(
                    select(StoryboardShot).where(
                        StoryboardShot.id.startswith(req.storyboard_shot_id)
                    )
                )
            if shot_row:
                scene_row = self.session.get(StoryboardScene, shot_row.scene_id)
                if not board and scene_row:
                    board = self.session.get(Storyboard, scene_row.storyboard_id)
                return [
                    {
                        "shot": shot_row.shot_config,
                        "scene": scene_row.scene_config if scene_row else None,
                        "global_direction": board.global_direction if board else req.global_direction,
                        "storyboard": board,
                    }
                ]
            # fallback: look inside document
            if board:
                for sc in (board.document or {}).get("scenes") or []:
                    for sh in sc.get("shots") or []:
                        if str(sh.get("id", "")).startswith(req.storyboard_shot_id):
                            return [
                                {
                                    "shot": sh,
                                    "scene": sc,
                                    "global_direction": board.global_direction,
                                    "storyboard": board,
                                }
                            ]
            raise ValueError("storyboard shot not found")

        assert board is not None
        if req.compile_all_shots:
            out: list[dict[str, Any]] = []
            for sc in (board.document or {}).get("scenes") or []:
                for sh in sc.get("shots") or []:
                    out.append(
                        {
                            "shot": sh,
                            "scene": sc,
                            "global_direction": board.global_direction,
                            "storyboard": board,
                        }
                    )
            if not out:
                raise ValueError("storyboard has no shots")
            return out

        # default: first shot
        for sc in (board.document or {}).get("scenes") or []:
            shots = sc.get("shots") or []
            if shots:
                return [
                    {
                        "shot": shots[0],
                        "scene": sc,
                        "global_direction": board.global_direction,
                        "storyboard": board,
                    }
                ]
        raise ValueError("storyboard has no shots")

    def _resolve_context(
        self,
        board: Storyboard | None,
        shot: dict[str, Any],
        scene: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        resolved = (board.document or {}).get("resolved_assets") if board else {}
        resolved = dict(resolved or {})
        char_ctx: dict[str, Any] = {}
        subject = shot.get("subject") or {}
        char_id = subject.get("character_id")
        reg = CharacterRegistry(self.session)
        char = reg.get(char_id) if char_id else None
        if not char and scene:
            for c in scene.get("characters") or []:
                if c.get("character_id"):
                    char = reg.get(c["character_id"])
                    if char:
                        break
        if char:
            char_ctx = {
                "id": char.id,
                "slug": char.slug,
                "name": char.name,
                "version": char.current_version,
                "current_version": char.current_version,
                "canonical_data": char.canonical_data,
            }
            resolved["character"] = {**(resolved.get("character") or {}), **char_ctx}
        return char_ctx, resolved


def compile_prompts(session: Session, request: CompileRequest | dict[str, Any]) -> list[PromptPackage]:
    return PromptService(session).compile(request)
