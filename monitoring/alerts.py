from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from config.settings import Settings, get_settings
from db.models import VideoRun
from db.session import get_session
from orchestration.state_machine import RunStatus

logger = logging.getLogger(__name__)


def _post_webhook(url: str, text: str) -> None:
    try:
        httpx.post(url, json={"text": text}, timeout=10.0)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send alert webhook")


def alert_pipeline_failure(run_id: int, error: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    message = f"[content-pipeline] video_run {run_id} FAILED: {error}"
    logger.error(message)
    if settings.alert_webhook_url:
        _post_webhook(settings.alert_webhook_url, message)


def alert_stale_qa(hours: int = 24, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    with get_session() as session:
        stale = session.scalars(
            select(VideoRun).where(
                VideoRun.status == RunStatus.QA_PENDING.value,
                VideoRun.updated_at < cutoff,
            )
        ).all()
        if stale and settings.alert_webhook_url:
            ids = ", ".join(str(r.id) for r in stale)
            _post_webhook(
                settings.alert_webhook_url,
                f"[content-pipeline] {len(stale)} video(s) in qa_pending >{hours}h: {ids}",
            )
        return len(stale)
