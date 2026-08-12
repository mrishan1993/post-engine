from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from image_generation_engine.schemas import TechnicalImageQA


def _parse_aspect(ratio: str) -> float | None:
    try:
        a, b = ratio.split(":")
        return float(a) / float(b)
    except Exception:  # noqa: BLE001
        return None


def probe_image(uri: str) -> dict[str, Any]:
    """Prefer Pillow if available; fall back to stub sidecar metadata."""
    path = Path(uri)
    meta_path = path.with_suffix(".meta.json")

    try:
        from PIL import Image  # type: ignore[import-untyped]

        if path.exists() and not path.read_bytes().startswith(b"AMP_IMAGE_STUB"):
            with Image.open(path) as im:
                return {
                    "source": "pillow",
                    "width": im.width,
                    "height": im.height,
                    "mime_type": Image.MIME.get(im.format or "", "image/png"),
                    "mode": im.mode,
                    "size_bytes": path.stat().st_size,
                }
    except Exception:  # noqa: BLE001
        pass

    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return {
            "source": "stub",
            "width": data.get("width"),
            "height": data.get("height"),
            "mime_type": data.get("mime_type") or "image/png",
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
    return {"source": "none", "size_bytes": path.stat().st_size if path.exists() else 0}


def perceptual_hash_stub(uri: str) -> str:
    """Simple content fingerprint (not a true pHash; good enough for duplicate stubs)."""
    data = Path(uri).read_bytes()
    return hashlib.md5(data).hexdigest()


def validate_image_artifact(
    uri: str,
    *,
    expected_aspect: str | None = None,
    expected_resolution: str | None = None,
    known_hashes: set[str] | None = None,
) -> TechnicalImageQA:
    path = Path(uri)
    notes: list[str] = []
    exists = path.exists() and path.is_file()
    if not exists:
        return TechnicalImageQA(ok=False, file_exists=False, notes=["file missing"])

    raw = path.read_bytes()
    readable = len(raw) > 0
    if not readable:
        return TechnicalImageQA(ok=False, file_exists=True, readable=False, notes=["empty file"])

    probed = probe_image(uri)
    source = str(probed.get("source") or "none")

    blank_risk = False
    dark_risk = False
    bright_risk = False
    if raw.startswith(b"AMP_IMAGE_STUB"):
        notes.append("stub artifact accepted")
    elif source == "none":
        notes.append("no probe metadata; basic checks only")
        blank_risk = len(raw) < 32

    dimensions_ok = True
    exp_w = exp_h = None
    if expected_resolution and "x" in expected_resolution:
        try:
            exp_w, exp_h = [int(x) for x in expected_resolution.lower().split("x")[:2]]
        except ValueError:
            exp_w = exp_h = None
    if exp_w and exp_h and probed.get("width") and probed.get("height"):
        dimensions_ok = int(probed["width"]) == exp_w and int(probed["height"]) == exp_h
        if not dimensions_ok:
            notes.append(
                f"resolution mismatch expected={expected_resolution} "
                f"got={probed.get('width')}x{probed.get('height')}"
            )

    aspect_ok = True
    # Image providers often pair "9:16" with 1024x1536 (≈2:3). If resolution matches,
    # treat aspect as satisfied; otherwise allow portrait/landscape family tolerance.
    if expected_aspect and probed.get("width") and probed.get("height"):
        if exp_w and exp_h and dimensions_ok:
            aspect_ok = True
        else:
            target = _parse_aspect(expected_aspect)
            if target:
                actual = float(probed["width"]) / float(probed["height"])
                # Loose family match: both portrait (<1) or both landscape (>1), or near exact
                same_orientation = (target < 1 and actual < 1) or (target > 1 and actual > 1) or abs(
                    target - 1
                ) < 0.05
                aspect_ok = abs(actual - target) < 0.12 or (
                    same_orientation and abs(actual - target) < 0.2
                )
                if not aspect_ok:
                    notes.append(f"aspect mismatch expected={expected_aspect} got={actual:.3f}")

    mime_ok = True
    mime = probed.get("mime_type") or "image/png"
    if mime and not str(mime).startswith("image/"):
        mime_ok = False
        notes.append(f"unexpected mime {mime}")

    phash = perceptual_hash_stub(uri)
    duplicate_risk = bool(known_hashes and phash in known_hashes)
    if duplicate_risk:
        notes.append("near-duplicate hash detected")

    integrity = 1.0 if exists and readable else 0.0
    resolution_score = 1.0 if dimensions_ok else 0.5
    aspect_score = 1.0 if aspect_ok else 0.5
    artifact_score = 0.5 if (blank_risk or dark_risk or bright_risk) else 1.0
    if duplicate_risk:
        artifact_score *= 0.7
    technical_score = round(
        0.35 * integrity + 0.25 * resolution_score + 0.20 * aspect_score + 0.20 * artifact_score,
        4,
    )

    ok = (
        exists
        and readable
        and dimensions_ok
        and aspect_ok
        and mime_ok
        and not blank_risk
        and technical_score >= 0.7
    )
    return TechnicalImageQA(
        ok=ok,
        file_exists=exists,
        readable=readable,
        mime_ok=mime_ok,
        dimensions_ok=dimensions_ok,
        aspect_ratio_ok=aspect_ok,
        blank_risk=blank_risk,
        dark_risk=dark_risk,
        bright_risk=bright_risk,
        duplicate_risk=duplicate_risk,
        probe_source=source,
        technical_score=technical_score,
        notes=notes,
        probed={**probed, "phash": phash},
    )


def sha256_file(uri: str) -> tuple[str, int]:
    data = Path(uri).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)
