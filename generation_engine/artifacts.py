from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from amp_platform.artifacts.registry import get_artifact_registry
from generation_engine.schemas import TechnicalQAResult


MIME_BY_EXT = {
    ".mp4": "video/mp4",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".bin": "application/octet-stream",
}


def validate_artifact(
    uri: str,
    *,
    modality: str,
    expected_duration: float | None = None,
) -> TechnicalQAResult:
    path = Path(uri)
    notes: list[str] = []
    exists = path.exists() and path.is_file()
    readable = False
    size = 0
    if exists:
        try:
            data = path.read_bytes()
            size = len(data)
            readable = size > 0
            if not data.startswith(b"AMP_STUB_ARTIFACT") and modality == "video":
                # real media would use ffprobe; stub accepts marker or any non-empty
                notes.append("non-stub payload; basic size check only")
        except OSError as exc:
            notes.append(str(exc))
            readable = False

    duration_valid = True
    if expected_duration is not None and expected_duration <= 0:
        duration_valid = False
        notes.append("invalid expected duration")

    ok = exists and readable and duration_valid
    return TechnicalQAResult(
        ok=ok,
        file_exists=exists,
        readable=readable,
        duration_valid=duration_valid,
        resolution_valid=True,
        size_bytes=size,
        notes=notes,
    )


def sha256_file(uri: str) -> tuple[str, int]:
    data = Path(uri).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def mime_for(uri: str) -> str:
    return MIME_BY_EXT.get(Path(uri).suffix.lower(), "application/octet-stream")


def register_platform_artifact(
    *,
    uri: str,
    artifact_type: str,
    job_id: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    rec = get_artifact_registry().register(
        type=artifact_type,
        uri=uri,
        source_service="generation-engine",
        parent_ids=[],
        metadata={"generation_job_id": job_id, **(metadata or {})},
    )
    return rec.artifact_id
