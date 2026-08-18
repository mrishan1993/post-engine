"""Live first-reel media — Replicate/Gemini stills, optional ElevenLabs VO.

Missing or broken providers are skipped with documented bypasses. The locked
2016-phone spec does not need Anthropic, Suno, Midjourney, or Instagram.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx

from config.settings import get_settings
from first_reel.spec import CAPTION, HOOK, PUNCHLINE, SHOTS

_STYLE = (
    "photorealistic amateur iPhone snapshot, 2016 digital photography, "
    "fingerprint smudges on the lens, slight motion blur, visible noise/grain, "
    "harsh on-camera flash or dim bedroom lamp, not cinematic, not studio, "
    "no text overlay, no watermark, no logo, vertical 9:16 composition"
)

_SHOT_PROMPTS: dict[int, str] = {
    1: (
        f"{_STYLE}. Close-up of a modern smartphone lying on rumpled bedsheets at night, "
        "lock screen glowing, fingerprints on glass, POV looking down at the phone, "
        "messy bedroom, warm lamp in the background."
    ),
    2: (
        f"{_STYLE}. First-person photo of an old iPhone 6 lock screen, iOS 9 aesthetic, "
        "date Saturday June 11 2016, slide to unlock, round home button, "
        "tiny crack in the corner of the glass, phone held in a hand."
    ),
    3: (
        f"{_STYLE}. Awkward 2016 bathroom-mirror flash selfie of a young millennial, "
        "front camera, red-eye, grainy, casual plaid shirt, duckface-adjacent, "
        "harsh on-camera flash, tiled bathroom behind."
    ),
    4: (
        f"{_STYLE}. Extreme close-up photograph of an iPhone screen showing old iMessage, "
        "green and blue bubbles, one message reading Life is good with a red heart, "
        "iOS 9 Messages UI, photoreal phone screen, no extra captions."
    ),
    5: (
        f"{_STYLE}. Cluttered 2016 teenage bedroom desk: iPhone with white wired earphones, "
        "music player open, Polaroids, another phone showing a silly Snapchat filter, "
        "warm tungsten light, nostalgic mess."
    ),
    6: (
        f"{_STYLE}. Dark empty bedroom at night, phone lying face-down on the bed, "
        "only dim streetlight through blinds, lonely sparse composition, no people."
    ),
    7: (
        f"{_STYLE}. Return to the old iPhone lock screen in a hand, iOS 9, date 2016, "
        "home button, fingerprints, looping back to the opening beat."
    ),
}


def _present(value: str | None) -> bool:
    return bool(value and str(value).strip())


def probe_tools() -> list[dict[str, Any]]:
    """Read-only key presence + live auth checks. Never returns secret values."""
    s = get_settings()
    rows: list[dict[str, Any]] = []

    def add(*, name: str, role: str, configured: bool, ok: bool, detail: str, impact: str, bypass: str) -> None:
        rows.append(
            {
                "name": name,
                "role": role,
                "configured": configured,
                "ok": ok,
                "detail": detail,
                "impact": impact,
                "bypass": bypass,
            }
        )

    timeout = httpx.Timeout(20.0, connect=8.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        add(
            name="anthropic",
            role="llm",
            configured=_present(s.anthropic_api_key),
            ok=False,
            detail="key empty",
            impact="Cannot rewrite script/briefs with Claude.",
            bypass="Locked first-reel spec; no LLM required for this slice.",
        )
        add(
            name="suno",
            role="music",
            configured=_present(s.suno_api_key),
            ok=False,
            detail="key empty",
            impact="Cannot generate original music.",
            bypass="Spec is platform_native — silent master; trend audio at publish.",
        )
        add(
            name="midjourney",
            role="image",
            configured=_present(s.midjourney_api_key),
            ok=False,
            detail="key empty",
            impact="No Midjourney stills.",
            bypass="Replicate Flux, then Gemini image.",
        )
        add(
            name="instagram",
            role="publish",
            configured=_present(s.instagram_access_token) and _present(s.instagram_user_id),
            ok=False,
            detail="token empty",
            impact="Cannot upload the reel to Instagram.",
            bypass="Write local MP4 package only.",
        )
        add(
            name="temp_hosting",
            role="ig_cdn",
            configured=_present(s.temp_hosting_base_url),
            ok=False,
            detail="empty",
            impact="Instagram Graph publish needs a public media URL.",
            bypass="Not needed until IG credentials exist.",
        )

        if _present(s.elevenlabs_api_key):
            r = client.get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": s.elevenlabs_api_key})
            add(
                name="elevenlabs",
                role="voice",
                configured=True,
                ok=r.status_code == 200,
                detail=f"HTTP {r.status_code}",
                impact="No voiceover sidecar if this fails.",
                bypass="Silent master is the intended deliverable.",
            )
        else:
            add(
                name="elevenlabs",
                role="voice",
                configured=False,
                ok=False,
                detail="key empty",
                impact="No VO sidecar.",
                bypass="Silent master.",
            )

        if _present(s.openai_api_key):
            r = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {s.openai_api_key}"},
            )
            add(
                name="openai",
                role="llm+image",
                configured=True,
                ok=r.status_code == 200,
                detail=f"HTTP {r.status_code}",
                impact="No OpenAI stills or script rewrite.",
                bypass="Replicate / Gemini stills; locked spec.",
            )
        else:
            add(
                name="openai",
                role="llm+image",
                configured=False,
                ok=False,
                detail="key empty",
                impact="No OpenAI stills.",
                bypass="Replicate / Gemini.",
            )

        if _present(s.fal_key):
            r = client.post(
                "https://queue.fal.run/fal-ai/flux/schnell",
                headers={"Authorization": f"Key {s.fal_key}", "Content-Type": "application/json"},
                json={},
            )
            ok = r.status_code in (200, 201, 202, 422, 400)
            add(
                name="fal",
                role="image",
                configured=True,
                ok=ok,
                detail=f"HTTP {r.status_code}",
                impact="No fal.ai stills.",
                bypass="Replicate / Gemini.",
            )
        else:
            add(
                name="fal",
                role="image",
                configured=False,
                ok=False,
                detail="key empty",
                impact="No fal.ai stills.",
                bypass="Replicate / Gemini.",
            )

        if _present(s.replicate_api_token):
            r = client.get(
                "https://api.replicate.com/v1/account",
                headers={"Authorization": f"Bearer {s.replicate_api_token}"},
            )
            add(
                name="replicate",
                role="image",
                configured=True,
                ok=r.status_code == 200,
                detail=f"HTTP {r.status_code}",
                impact="Primary still generator unavailable.",
                bypass="Gemini native image.",
            )
        else:
            add(
                name="replicate",
                role="image",
                configured=False,
                ok=False,
                detail="key empty",
                impact="Need another image provider.",
                bypass="Gemini native image.",
            )

        if _present(s.google_api_key):
            r = client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": s.google_api_key},
            )
            add(
                name="google_gemini",
                role="llm+image",
                configured=True,
                ok=r.status_code == 200,
                detail=f"HTTP {r.status_code}",
                impact="No Gemini fallback stills.",
                bypass="Replicate Flux.",
            )
        else:
            add(
                name="google_gemini",
                role="llm+image",
                configured=False,
                ok=False,
                detail="key empty",
                impact="No Gemini fallback.",
                bypass="Replicate Flux.",
            )

        if _present(s.runway_api_key):
            r = client.get(
                "https://api.dev.runwayml.com/v1/organization",
                headers={
                    "Authorization": f"Bearer {s.runway_api_key}",
                    "X-Runway-Version": "2024-11-06",
                },
            )
            add(
                name="runway",
                role="video",
                configured=True,
                ok=r.status_code == 200,
                detail=f"HTTP {r.status_code}",
                impact="No generative video clips (min clip length mismatches 1–2.5s shots).",
                bypass="Ken Burns / push-in on stills via ffmpeg.",
            )
        else:
            add(
                name="runway",
                role="video",
                configured=False,
                ok=False,
                detail="key empty",
                impact="No generative video clips.",
                bypass="Ken Burns stills.",
            )

        if _present(s.youtube_api_key):
            r = client.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "id", "chart": "mostPopular", "maxResults": 1, "key": s.youtube_api_key},
            )
            add(
                name="youtube_data",
                role="trends",
                configured=True,
                ok=r.status_code == 200,
                detail=f"HTTP {r.status_code}",
                impact="Live trend ingest unavailable.",
                bypass="Locked 2026-is-the-new-2016 spec.",
            )
        else:
            add(
                name="youtube_data",
                role="trends",
                configured=False,
                ok=False,
                detail="key empty",
                impact="No live YouTube trends.",
                bypass="Locked spec.",
            )

        oauth_ready = all(
            _present(x) for x in (s.youtube_client_id, s.youtube_client_secret, s.youtube_refresh_token)
        )
        if oauth_ready:
            r = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": s.youtube_client_id,
                    "client_secret": s.youtube_client_secret,
                    "refresh_token": s.youtube_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            add(
                name="youtube_oauth",
                role="publish",
                configured=True,
                ok=r.status_code == 200,
                detail=f"HTTP {r.status_code}",
                impact="Cannot upload to YouTube.",
                bypass="Local MP4 only for this run.",
            )
        else:
            add(
                name="youtube_oauth",
                role="publish",
                configured=False,
                ok=False,
                detail="oauth incomplete",
                impact="Cannot upload to YouTube.",
                bypass="Local MP4 only.",
            )
    return rows


def _download(client: httpx.Client, url: str, dest: Path) -> None:
    r = client.get(url)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)


class NoCreditsError(RuntimeError):
    """Provider authenticated but has no remaining credits/quota to generate."""


def _replicate_predict(client: httpx.Client, token: str, model: str, prompt: str) -> str:
    r = client.post(
        f"https://api.replicate.com/v1/models/{model}/predictions",
        headers={
            "Authorization": f"Bearer {token}",
            "Prefer": "wait=60",
            "Content-Type": "application/json",
        },
        json={
            "input": {
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "output_format": "png",
                "output_quality": 90,
                "num_outputs": 1,
                "go_fast": True,
            }
        },
        timeout=90.0,
    )
    if r.status_code == 402:
        raise NoCreditsError(f"replicate {model} HTTP 402: no credits")
    if r.status_code >= 400:
        raise RuntimeError(f"replicate {model} HTTP {r.status_code}: {r.text[:400]}")
    data = r.json()
    status = data.get("status")
    get_url = (data.get("urls") or {}).get("get")
    deadline = time.time() + 180
    while status in {"starting", "processing"} and get_url and time.time() < deadline:
        time.sleep(2)
        poll = client.get(get_url, headers={"Authorization": f"Bearer {token}"})
        poll.raise_for_status()
        data = poll.json()
        status = data.get("status")
    if status != "succeeded":
        err = data.get("error") or data.get("status")
        raise RuntimeError(f"replicate {model} failed: {err}")
    output = data.get("output")
    if isinstance(output, list) and output:
        return str(output[0])
    if isinstance(output, str) and output:
        return output
    raise RuntimeError(f"replicate {model} returned no image URL")


def _gemini_image(client: httpx.Client, api_key: str, prompt: str) -> bytes:
    """Single cheap image model + 429 backoff. Do not fan out across paid previews."""
    model = "gemini-2.5-flash-image"
    last_err = "gemini image not attempted"
    for attempt in range(3):
        r = client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {"aspectRatio": "9:16"},
                },
            },
            timeout=90.0,
        )
        if r.status_code == 429:
            wait = 12 * (attempt + 1)
            last_err = f"{model} HTTP 429"
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{model} HTTP {r.status_code}: {r.text[:300]}")
        for cand in r.json().get("candidates") or []:
            for part in ((cand.get("content") or {}).get("parts") or []):
                inline = part.get("inlineData") or part.get("inline_data") or {}
                data = inline.get("data")
                if data:
                    return base64.b64decode(data)
        last_err = f"{model} returned no image bytes"
        break
    raise RuntimeError(last_err)


def generate_live_frames(out_dir: Path) -> list[dict[str, Any]]:
    """Generate 9:16 stills for each shot. Replicate first, Gemini fallback."""
    settings = get_settings()
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(settings.storage_root) / "first_reel" / "_live_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    errors: list[str] = []
    provider_used: str | None = None

    timeout = httpx.Timeout(90.0, connect=15.0)
    replicate_disabled = False
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for shot in SHOTS:
            shot_n = int(shot["shot"])
            label = str(shot["label"])
            prompt = _SHOT_PROMPTS[shot_n]
            dest = out_dir / f"shot_{shot_n:02d}_{label.lower()}.png"
            cache = cache_dir / dest.name
            used = None
            last_err = None

            if dest.exists() and dest.stat().st_size > 1000:
                used = "cached"
            elif cache.exists() and cache.stat().st_size > 1000:
                dest.write_bytes(cache.read_bytes())
                used = "cached"
            elif not replicate_disabled and _present(settings.replicate_api_token):
                for model in ("black-forest-labs/flux-schnell",):
                    try:
                        url = _replicate_predict(client, settings.replicate_api_token or "", model, prompt)
                        _download(client, url, dest)
                        used = f"replicate:{model}"
                        break
                    except NoCreditsError as exc:
                        replicate_disabled = True
                        last_err = str(exc)
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_err = f"{model}: {exc}"

            if used is None and _present(settings.google_api_key):
                try:
                    dest.write_bytes(_gemini_image(client, settings.google_api_key or "", prompt))
                    used = "gemini:flash-image"
                    time.sleep(4)
                except Exception as exc:  # noqa: BLE001
                    last_err = f"gemini: {exc}"

            if used is None or not dest.exists() or dest.stat().st_size < 1000:
                errors.append(f"shot {shot_n} ({label}): {last_err or 'no image provider succeeded'}")
                continue

            provider_used = used
            if dest.exists() and dest.stat().st_size > 1000:
                cache.write_bytes(dest.read_bytes())
            card = out_dir / f"shot_{shot_n:02d}_card.json"
            meta = {
                **shot,
                "frame": str(dest),
                "visual_kind": "live_api",
                "provider": used,
                "prompt": prompt,
                "safe_area": {"top": 180, "bottom": 220, "left": 64, "right": 64},
            }
            card.write_text(json.dumps(meta, indent=2))
            frames.append({"shot": shot_n, "frame": str(dest), "card": str(card), **shot, "visual_kind": "live_api", "provider": used})

    by_shot = {int(f["shot"]): f for f in frames}

    def _copy_shot(src_n: int, dest_shot: dict[str, Any], reason: str) -> None:
        src = by_shot.get(src_n)
        if not src:
            return
        shot_n = int(dest_shot["shot"])
        label = str(dest_shot["label"])
        dest = out_dir / f"shot_{shot_n:02d}_{label.lower()}.png"
        dest.write_bytes(Path(src["frame"]).read_bytes())
        card = out_dir / f"shot_{shot_n:02d}_card.json"
        meta = {
            **dest_shot,
            "frame": str(dest),
            "visual_kind": "live_api",
            "provider": f"reuse_shot_{src_n}:{reason}",
            "safe_area": {"top": 180, "bottom": 220, "left": 64, "right": 64},
        }
        card.write_text(json.dumps(meta, indent=2))
        item = {
            "shot": shot_n,
            "frame": str(dest),
            "card": str(card),
            **dest_shot,
            "visual_kind": "live_api",
            "provider": meta["provider"],
        }
        frames.append(item)
        by_shot[shot_n] = item

    # Spec-legal bypasses if image quota is exhausted:
    # LOOP returns to the unlock beat; PUNCHLINE is a sparse/dark hold.
    if 7 not in by_shot and 2 in by_shot:
        _copy_shot(2, SHOTS[6], "loop_returns_to_unlock")
    elif 7 not in by_shot and 1 in by_shot:
        _copy_shot(1, SHOTS[6], "loop_returns_to_hook")
    if 6 not in by_shot and 1 in by_shot:
        _copy_shot(1, SHOTS[5], "punchline_sparse_reuse")

    if len(by_shot) < len(SHOTS):
        from amp_platform.procedural_media import compose_shot_plate

        for shot in SHOTS:
            shot_n = int(shot["shot"])
            if shot_n in by_shot:
                continue
            label = str(shot["label"])
            dest = out_dir / f"shot_{shot_n:02d}_{label.lower()}.png"
            compose_shot_plate(dest, label=label, width=1080, height=1920, seed=2016 + shot_n)
            card = out_dir / f"shot_{shot_n:02d}_card.json"
            meta = {
                **shot,
                "frame": str(dest),
                "visual_kind": "procedural_fallback",
                "provider": "procedural_bypass",
                "safe_area": {"top": 180, "bottom": 220, "left": 64, "right": 64},
            }
            card.write_text(json.dumps(meta, indent=2))
            item = {
                "shot": shot_n,
                "frame": str(dest),
                "card": str(card),
                **shot,
                "visual_kind": "procedural_fallback",
                "provider": "procedural_bypass",
            }
            frames.append(item)
            by_shot[shot_n] = item
            errors.append(f"shot {shot_n} ({label}): used procedural bypass")

    frames.sort(key=lambda f: int(f["shot"]))

    (out_dir / "live_meta.json").write_text(
        json.dumps({"provider": provider_used, "errors": errors, "shots": len(frames)}, indent=2)
    )
    return frames


def generate_voiceover(out_dir: Path) -> str | None:
    """Optional sidecar VO. Not muxed into the silent master."""
    settings = get_settings()
    if not _present(settings.elevenlabs_api_key) or not _present(settings.elevenlabs_voice_id):
        return None
    text = f"{HOOK}. {PUNCHLINE} {CAPTION}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "voiceover.mp3"
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}",
            headers={
                "xi-api-key": settings.elevenlabs_api_key or "",
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
            json={"text": text, "model_id": "eleven_multilingual_v2"},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"elevenlabs HTTP {r.status_code}: {r.text[:300]}")
        dest.write_bytes(r.content)
    return str(dest)
