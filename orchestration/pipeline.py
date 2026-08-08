from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.assembly_agent import AssemblyAgent
from agents.audio_agent import AudioAgent
from agents.base import Agent, AgentResult
from agents.publishing_agent import PublishingAgent
from agents.safety_qa_agent import SafetyQAAgent
from agents.topic_script_agent import TopicScriptAgent
from agents.visual_agent import VisualAgent
from amp_platform.events import EventType, get_bus
from amp_platform.events.types import (
    VideoApproved,
    VideoCreated,
    VideoPublished,
    VideoRejected,
)
from config.loader import load_global_config, load_vertical_config
from config.schema import VerticalConfig
from config.settings import Settings, get_settings
from db.models import AgentRunLog, ContentBrief, Publication, Vertical, VideoRun
from monitoring.alerts import alert_pipeline_failure
from orchestration.retry import retry
from orchestration.state_machine import (
    RESUME_FROM,
    RunStatus,
    assert_transition,
    parse_regen_from,
)
from providers.instagram_provider import InstagramGraphProvider, StubInstagramProvider
from providers.llm_provider import AnthropicLLMProvider, StubLLMProvider
from providers.music_provider import StubMusicProvider, SunoMusicProvider
from providers.tts_provider import ElevenLabsTTSProvider, StubTTSProvider
from providers.youtube_provider import StubYouTubeProvider, YouTubeDataAPIProvider


class Pipeline:
    def __init__(self, session: Session, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()
        self.global_config = load_global_config()
        self.agents = self._wire_agents()

    def _wire_agents(self) -> dict[str, Agent]:
        if self.settings.pipeline_stub_providers:
            llm = StubLLMProvider()
            tts = StubTTSProvider()
            music = StubMusicProvider()
            youtube = StubYouTubeProvider()
            instagram = StubInstagramProvider()
        else:
            if not self.settings.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY required when stubs are disabled")
            llm = AnthropicLLMProvider(api_key=self.settings.anthropic_api_key)
            tts = ElevenLabsTTSProvider(
                api_key=self.settings.elevenlabs_api_key or "",
                default_voice_id=self.settings.elevenlabs_voice_id,
            )
            music = SunoMusicProvider(api_key=self.settings.suno_api_key or "")
            youtube = YouTubeDataAPIProvider(
                client_id=self.settings.youtube_client_id or "",
                client_secret=self.settings.youtube_client_secret or "",
                refresh_token=self.settings.youtube_refresh_token or "",
            )
            instagram = InstagramGraphProvider(
                access_token=self.settings.instagram_access_token or "",
                user_id=self.settings.instagram_user_id or "",
                temp_hosting_base_url=self.settings.temp_hosting_base_url,
            )

        return {
            "script": TopicScriptAgent(llm=llm),
            "audio": AudioAgent(tts=tts, music=music),
            "visual": VisualAgent(),
            "assembly": AssemblyAgent(),
            "safety_qa": SafetyQAAgent(llm=llm),
            "publishing": PublishingAgent(youtube=youtube, instagram=instagram),
        }

    def ensure_vertical(self, slug: str) -> Vertical:
        vertical = self.session.scalar(select(Vertical).where(Vertical.slug == slug))
        if vertical:
            return vertical
        cfg = load_vertical_config(slug)
        vertical = Vertical(
            slug=cfg.slug,
            display_name=cfg.display_name,
            config_path=f"config/verticals/{slug}.yaml",
            is_active=True,
        )
        self.session.add(vertical)
        self.session.flush()
        return vertical

    def enqueue_brief(
        self,
        vertical_slug: str,
        brief_text: str,
        *,
        priority: int = 0,
        source: str = "manual",
    ) -> ContentBrief:
        vertical = self.ensure_vertical(vertical_slug)
        brief = ContentBrief(
            vertical_id=vertical.id,
            brief_text=brief_text,
            priority=priority,
            status="pending",
            source=source,
        )
        self.session.add(brief)
        self.session.flush()
        return brief

    def create_run(self, brief: ContentBrief) -> VideoRun:
        run = VideoRun(
            brief_id=brief.id,
            vertical_id=brief.vertical_id,
            status=RunStatus.CREATED.value,
        )
        brief.status = "in_progress"
        self.session.add(run)
        self.session.flush()
        Path(f"storage/raw/{run.id}").mkdir(parents=True, exist_ok=True)
        return run

    def _transition(self, run: VideoRun, target: RunStatus) -> None:
        assert_transition(run.status, target)
        run.status = target.value
        run.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    def _log_agent(
        self,
        run: VideoRun,
        agent_name: str,
        result: AgentResult,
        attempt_number: int,
        input_summary: str,
    ) -> None:
        self.session.add(
            AgentRunLog(
                video_run_id=run.id,
                agent_name=agent_name,
                input_summary=input_summary[:2000],
                output_summary=json.dumps(result.output)[:2000] if result.output else None,
                cost_usd=result.cost_usd,
                duration_ms=result.duration_ms,
                attempt_number=attempt_number,
                success=result.success,
                error_message=result.error,
            )
        )
        run.total_cost_usd = float(run.total_cost_usd or 0) + float(result.cost_usd or 0)
        self.session.flush()

    def _run_agent_with_retry(
        self,
        agent_key: str,
        run: VideoRun,
        vertical_config: VerticalConfig,
        context: dict[str, Any],
    ) -> AgentResult:
        agent = self.agents[agent_key]
        retry_cfg = self.global_config.get("retry", {}).get(agent_key, {})
        max_attempts = int(retry_cfg.get("max_attempts", 1))
        backoff = tuple(retry_cfg.get("backoff_seconds", [5]))

        @retry(max_attempts=max_attempts, backoff_seconds=backoff)
        def _call(attempt_number: int = 1) -> AgentResult:
            result = agent.run(
                video_run_id=run.id,
                vertical_config=vertical_config,
                context=context,
                attempt_number=attempt_number,
            )
            self._log_agent(
                run,
                agent.name,
                result,
                attempt_number,
                input_summary=json.dumps({k: context.get(k) for k in sorted(context)[:8]}),
            )
            if not result.success:
                raise RuntimeError(result.error or f"{agent.name} failed")
            return result

        return _call()

    def _context_from_run(self, run: VideoRun, brief: ContentBrief) -> dict[str, Any]:
        return {
            "brief_text": brief.brief_text,
            "script": run.script_text,
            "title": run.title,
            "description": run.description,
            "tags": list(run.tags or []),
            "audio_asset_path": run.audio_asset_path,
            "audio_duration_sec": run.audio_duration_sec,
            "visual_asset_path": run.visual_asset_path,
            "rendered_video_path": run.rendered_video_path,
        }

    def run_until_qa(self, run_id: int) -> VideoRun:
        run = self.session.get(VideoRun, run_id)
        if not run:
            raise ValueError(f"video_run {run_id} not found")
        brief = self.session.get(ContentBrief, run.brief_id)
        vertical = self.session.get(Vertical, run.vertical_id)
        if not brief or not vertical:
            raise ValueError("missing brief/vertical")

        vertical_config = load_vertical_config(vertical.slug)
        context = self._context_from_run(run, brief)
        start_stage = RESUME_FROM.get(RunStatus(run.status))
        if start_stage is None:
            raise ValueError(f"Cannot auto-run from status {run.status}")

        stages = [
            ("script", RunStatus.SCRIPT_DONE, self._apply_script),
            ("audio", RunStatus.AUDIO_DONE, self._apply_audio),
            ("visual", RunStatus.VISUAL_DONE, self._apply_visual),
            ("assembly", RunStatus.ASSEMBLED, self._apply_assembly),
            ("safety_qa", RunStatus.QA_PENDING, self._apply_safety),
        ]

        started = False
        try:
            for key, target, applier in stages:
                if not started:
                    if key != start_stage:
                        continue
                    started = True
                result = self._run_agent_with_retry(key, run, vertical_config, context)
                applier(run, result, context)
                self._transition(run, target)
            brief.status = "done"
            self.session.flush()
            get_bus().publish(
                EventType.VIDEO_CREATED,
                VideoCreated(
                    video_run_id=run.id,
                    brief_id=run.brief_id,
                    rendered_path=run.rendered_video_path,
                ),
                producer="generation-service",
            )
            return run
        except Exception as exc:  # noqa: BLE001
            run.error_log = str(exc)
            if can_fail(run.status):
                self._transition(run, RunStatus.FAILED)
            else:
                run.status = RunStatus.FAILED.value
            alert_pipeline_failure(run.id, str(exc), self.settings)
            self.session.flush()
            raise

    def _apply_script(self, run: VideoRun, result: AgentResult, context: dict[str, Any]) -> None:
        run.title = result.output["title"]
        run.description = result.output["description"]
        run.tags = result.output["tags"]
        run.script_text = result.output["script"]
        context.update(
            {
                "title": run.title,
                "description": run.description,
                "tags": run.tags,
                "script": run.script_text,
            }
        )

    def _apply_audio(self, run: VideoRun, result: AgentResult, context: dict[str, Any]) -> None:
        run.audio_asset_path = result.output["audio_asset_path"]
        run.audio_duration_sec = int(result.output["audio_duration_sec"])
        context["audio_asset_path"] = run.audio_asset_path
        context["audio_duration_sec"] = run.audio_duration_sec

    def _apply_visual(self, run: VideoRun, result: AgentResult, context: dict[str, Any]) -> None:
        run.visual_asset_path = result.output["visual_asset_path"]
        context["visual_asset_path"] = run.visual_asset_path

    def _apply_assembly(self, run: VideoRun, result: AgentResult, context: dict[str, Any]) -> None:
        run.rendered_video_path = result.output["rendered_video_path"]
        context["rendered_video_path"] = run.rendered_video_path

    def _apply_safety(self, run: VideoRun, result: AgentResult, context: dict[str, Any]) -> None:
        run.safety_check_result = result.output["safety_check_result"]

    def approve(self, run_id: int, reviewer: str) -> VideoRun:
        run = self._require_status(run_id, RunStatus.QA_PENDING)
        run.qa_reviewer = reviewer
        run.qa_decided_at = datetime.now(timezone.utc)
        self._transition(run, RunStatus.QA_APPROVED)
        get_bus().publish(
            EventType.VIDEO_APPROVED,
            VideoApproved(video_run_id=run.id, reviewer=reviewer, qa_notes=run.qa_notes),
            producer="qa-service",
        )
        return run

    def reject(self, run_id: int, reviewer: str, reason: str) -> VideoRun:
        run = self._require_status(run_id, RunStatus.QA_PENDING)
        run.qa_reviewer = reviewer
        run.qa_notes = reason
        run.qa_decided_at = datetime.now(timezone.utc)
        self._transition(run, RunStatus.QA_REJECTED)
        get_bus().publish(
            EventType.VIDEO_REJECTED,
            VideoRejected(video_run_id=run.id, reviewer=reviewer, reason=reason),
            producer="qa-service",
        )
        return run

    def publish(self, run_id: int) -> VideoRun:
        run = self._require_status(run_id, RunStatus.QA_APPROVED)
        brief = self.session.get(ContentBrief, run.brief_id)
        vertical = self.session.get(Vertical, run.vertical_id)
        assert brief and vertical
        vertical_config = load_vertical_config(vertical.slug)
        # Enforce gate at state-machine level: only qa_approved can publish.
        context = self._context_from_run(run, brief)
        result = self._run_agent_with_retry("publishing", run, vertical_config, context)
        pubs = result.output.get("publications", {})
        publication_ids: list[int] = []
        for platform_name, payload in pubs.items():
            pub = Publication(
                video_run_id=run.id,
                platform=platform_name,
                platform_post_id=payload.get("platform_post_id"),
                published_at=datetime.now(timezone.utc),
                platform_metadata=payload,
                status=payload.get("status", "published"),
            )
            self.session.add(pub)
            self.session.flush()
            publication_ids.append(pub.id)
        self._transition(run, RunStatus.PUBLISHED)
        get_bus().publish(
            EventType.VIDEO_PUBLISHED,
            VideoPublished(
                video_run_id=run.id,
                platforms=list(pubs.keys()),
                publication_ids=publication_ids,
            ),
            producer="publishing-service",
        )
        return run

    def regen(self, run_id: int, from_status: str) -> VideoRun:
        parent = self.session.get(VideoRun, run_id)
        if not parent:
            raise ValueError(f"video_run {run_id} not found")
        if parent.status != RunStatus.QA_REJECTED.value:
            raise ValueError("regen only allowed from qa_rejected runs")
        start = parse_regen_from(from_status)
        child = VideoRun(
            brief_id=parent.brief_id,
            vertical_id=parent.vertical_id,
            parent_run_id=parent.id,
            status=start.value,
            tags=[],
        )
        # Copy completed artifacts up to the resume point to avoid re-spend.
        if start in {
            RunStatus.SCRIPT_DONE,
            RunStatus.AUDIO_DONE,
            RunStatus.VISUAL_DONE,
            RunStatus.ASSEMBLED,
        }:
            child.script_text = parent.script_text
            child.title = parent.title
            child.description = parent.description
            child.tags = list(parent.tags or [])
        if start in {RunStatus.AUDIO_DONE, RunStatus.VISUAL_DONE, RunStatus.ASSEMBLED}:
            child.audio_asset_path = parent.audio_asset_path
            child.audio_duration_sec = parent.audio_duration_sec
        if start in {RunStatus.VISUAL_DONE, RunStatus.ASSEMBLED}:
            child.visual_asset_path = parent.visual_asset_path
        if start == RunStatus.ASSEMBLED:
            child.rendered_video_path = parent.rendered_video_path

        self.session.add(child)
        self.session.flush()
        Path(f"storage/raw/{child.id}").mkdir(parents=True, exist_ok=True)
        return child

    def _require_status(self, run_id: int, status: RunStatus) -> VideoRun:
        run = self.session.get(VideoRun, run_id)
        if not run:
            raise ValueError(f"video_run {run_id} not found")
        if run.status != status.value:
            raise ValueError(f"expected status {status.value}, got {run.status}")
        return run


def can_fail(status: str) -> bool:
    try:
        assert_transition(status, RunStatus.FAILED)
        return True
    except ValueError:
        return False
