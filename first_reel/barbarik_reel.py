"""One-off Barbarik / Khatu Shyam story reel generator."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from amp_platform.live_videos import available_video_backends, generate_video
from amp_platform.procedural_media import resolve_ffmpeg
from first_reel.live import _replicate_predict, _download

CONTENT_ID = "barbarik_khatu_shyam"
HOOK = "He had only three arrows."
PUNCHLINE = "Haare ka sahara."
CAPTION = "Barbarik. The warrior who gave his head — and became Khatu Shyam."
HASHTAGS = ["#KhatuShyam", "#Barbarik", "#Mahabharata", "#HaareKaSahara"]

VO_SCRIPT = (
    "Before Kurukshetra began, a young warrior walked toward the battlefield. "
    "Barbarik, Bhima's grandson. He carried just three arrows — a gift from Shiva. "
    "The first marked every target. The second destroyed them all. "
    "His vow: he would always fight for the side that was losing. "
    "Krishna, disguised as a Brahmin, asked — with only three arrows? "
    "Barbarik shot one. It pierced every leaf on a peepal tree. "
    "It even circled Krishna's foot, because a leaf was hidden beneath. "
    "Krishna understood the danger. Whichever side Barbarik joined would start losing, "
    "so he would switch sides again and again, until only Barbarik remained. "
    "So Krishna asked for one gift: his head. "
    "Barbarik gave it without hesitation. His only wish was to watch the war. "
    "When it ended, the Pandavas asked who deserved the credit. "
    "Barbarik said: I saw only Krishna's Sudarshan Chakra cutting through everyone, "
    "and Draupadi's anger drinking the blood. "
    "Today he is worshipped as Khatu Shyam. Haare ka sahara. The support of the defeated."
)

_STYLE = (
    "cinematic mythological Indian epic, dramatic volumetric light, "
    "ancient Kurukshetra atmosphere, photoreal digital painting, "
    "vertical 9:16 composition, no text overlay, no watermark, no modern objects"
)

SHOTS: list[dict[str, Any]] = [
    {
        "shot": 1,
        "label": "WALK",
        "weight": 1.1,
        "text": "Before Kurukshetra…",
        "prompt": (
            f"{_STYLE}. A young warrior Barbarik walking alone toward a vast dusty battlefield at dawn, "
            "bow on his back, saffron and earth-toned armor, wind in his hair, epic wide shot."
        ),
    },
    {
        "shot": 2,
        "label": "ARROWS",
        "weight": 1.0,
        "text": "Three arrows. Gift of Shiva.",
        "prompt": (
            f"{_STYLE}. Close-up of three divine glowing arrows in a young warrior's hand, "
            "golden divine light, carved wood and celestial energy, sacred aura."
        ),
    },
    {
        "shot": 3,
        "label": "VOW",
        "weight": 1.0,
        "text": "Always for the side that is losing.",
        "prompt": (
            f"{_STYLE}. Young warrior Barbarik kneeling in vow before a battlefield shrine, "
            "eyes fierce with resolve, incense smoke, sacred oath atmosphere."
        ),
    },
    {
        "shot": 4,
        "label": "KRISHNA",
        "weight": 1.1,
        "text": "With only three arrows?",
        "prompt": (
            f"{_STYLE}. Krishna disguised as a humble Brahmin stopping a young warrior on a dusty road, "
            "peacock-feather hint subtle, golden hour, confrontation of destiny."
        ),
    },
    {
        "shot": 5,
        "label": "LEAVES",
        "weight": 1.2,
        "text": "One arrow. Every leaf.",
        "prompt": (
            f"{_STYLE}. A single divine arrow streaking through a giant peepal tree, "
            "piercing every leaf in a magical cascade of light, mystical forest clearing."
        ),
    },
    {
        "shot": 6,
        "label": "FOOT",
        "weight": 1.0,
        "text": "Even the leaf under Krishna's foot.",
        "prompt": (
            f"{_STYLE}. Extreme close-up of a divine arrow circling a bare foot pressing a hidden leaf "
            "into the earth, golden dust, miraculous precision, sacred tension."
        ),
    },
    {
        "shot": 7,
        "label": "GIFT",
        "weight": 1.2,
        "text": "Krishna asked for his head.",
        "prompt": (
            f"{_STYLE}. Young warrior Barbarik offering his head in devotion to Krishna, "
            "serene sacrifice, divine glow, emotional mythological climax, respectful and sacred."
        ),
    },
    {
        "shot": 8,
        "label": "HILL",
        "weight": 1.0,
        "text": "He only wished to watch.",
        "prompt": (
            f"{_STYLE}. A sacred severed head of a warrior placed on a rocky hilltop overlooking "
            "the Kurukshetra battlefield below, twilight, solemn and divine, not gory."
        ),
    },
    {
        "shot": 9,
        "label": "CHAKRA",
        "weight": 1.1,
        "text": "I saw only Krishna's Chakra.",
        "prompt": (
            f"{_STYLE}. Krishna's blazing Sudarshan Chakra spinning through a chaotic battlefield, "
            "divine blue light cutting through warriors, epic mythological spectacle."
        ),
    },
    {
        "shot": 10,
        "label": "KHATU",
        "weight": 1.3,
        "text": "Khatu Shyam. Haare ka sahara.",
        "prompt": (
            f"{_STYLE}. Devotional portrait of Khatu Shyam as a serene blue-toned divine youth with "
            "turban and tilak, temple glow, marigold flowers, warm bhakti atmosphere, worshipful."
        ),
    },
]


def _load_dotenv() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _escape_drawtext(text: str) -> str:
    cleaned = text.replace("…", "...").replace("\n", " ").strip()
    return (
        cleaned.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _fontfile() -> str:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if Path(candidate).is_file():
            return candidate
    return "/System/Library/Fonts/Supplemental/Arial.ttf"


def _out_root() -> Path:
    root = Path("storage/first_reel") / CONTENT_ID
    root.mkdir(parents=True, exist_ok=True)
    (root / "frames").mkdir(exist_ok=True)
    return root


def generate_stills(frames_dir: Path) -> list[dict[str, Any]]:
    token = os.environ.get("REPLICATE_API_TOKEN") or ""
    if not token:
        raise RuntimeError("REPLICATE_API_TOKEN missing")
    frames: list[dict[str, Any]] = []
    with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0), follow_redirects=True) as client:
        for shot in SHOTS:
            shot_n = int(shot["shot"])
            label = str(shot["label"]).lower()
            dest = frames_dir / f"shot_{shot_n:02d}_{label}.png"
            print(f"[still] shot {shot_n} {shot['label']}", flush=True)
            if dest.exists() and dest.stat().st_size > 1000:
                used = "cached"
            else:
                used = None
                last_err = None
                for attempt in range(8):
                    try:
                        url = _replicate_predict(
                            client, token, "black-forest-labs/flux-schnell", shot["prompt"]
                        )
                        _download(client, url, dest)
                        used = "replicate:flux-schnell"
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_err = str(exc)
                        wait = 10 + attempt * 3
                        m = re.search(r"resets in ~(\d+)s", last_err)
                        if m:
                            wait = int(m.group(1)) + 3
                        print(f"  retry {attempt+1}: sleep {wait}s ({last_err[:140]})", flush=True)
                        time.sleep(wait)
                if used is None and os.environ.get("FAL_KEY"):
                    try:
                        from amp_platform.fal_images import generate_image as fal_generate

                        fal_generate(shot["prompt"], width=1080, height=1920, out_path=dest)
                        used = "fal:flux-schnell"
                    except Exception as exc:  # noqa: BLE001
                        last_err = f"{last_err} | fal: {exc}"
                if used is None and os.environ.get("OPENAI_API_KEY"):
                    try:
                        from amp_platform.openai_images import generate_image as openai_generate

                        openai_generate(shot["prompt"], width=1080, height=1920, out_path=dest)
                        used = "openai:images"
                    except Exception as exc:  # noqa: BLE001
                        last_err = f"{last_err} | openai: {exc}"
                if used is None:
                    raise RuntimeError(f"still failed for shot {shot_n}: {last_err}")
                time.sleep(11)
            card = {
                **shot,
                "frame": str(dest),
                "visual_kind": "live_api",
                "provider": used,
            }
            (frames_dir / f"shot_{shot_n:02d}_card.json").write_text(json.dumps(card, indent=2))
            frames.append(card)
            print(f"  ok {used} {dest.stat().st_size}", flush=True)
    return frames


def _replicate_upload_image(client: httpx.Client, token: str, path: Path) -> str:
    with path.open("rb") as f:
        up = client.post(
            "https://api.replicate.com/v1/files",
            headers={"Authorization": f"Bearer {token}"},
            files={"content": (path.name, f, "image/png")},
        )
    if up.status_code >= 400:
        raise RuntimeError(f"replicate file upload {up.status_code}: {up.text[:300]}")
    return str(up.json()["urls"]["get"])


def _replicate_wan_i2v(
    client: httpx.Client,
    token: str,
    *,
    image_url: str,
    prompt: str,
    out_path: Path,
) -> None:
    r = client.post(
        "https://api.replicate.com/v1/models/wan-video/wan-2.2-i2v-fast/predictions",
        headers={
            "Authorization": f"Bearer {token}",
            "Prefer": "wait=60",
            "Content-Type": "application/json",
        },
        json={
            "input": {
                "image": image_url,
                "prompt": prompt[:1500],
                "resolution": "480p",
                "num_frames": 81,
                "frames_per_second": 16,
                "interpolate_output": True,
                "go_fast": True,
            }
        },
        timeout=300.0,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"wan i2v submit {r.status_code}: {r.text[:400]}")
    data = r.json()
    status = data.get("status")
    get_url = (data.get("urls") or {}).get("get")
    while status in {"starting", "processing"} and get_url:
        time.sleep(3)
        data = client.get(get_url, headers={"Authorization": f"Bearer {token}"}).json()
        status = data.get("status")
    if status != "succeeded":
        raise RuntimeError(f"wan i2v failed: {data.get('error') or status}")
    out = data.get("output")
    url = out[0] if isinstance(out, list) else out
    if not url:
        raise RuntimeError(f"wan i2v no output: {data}")
    out_path.write_bytes(client.get(str(url)).content)


def generate_clips(frames_dir: Path, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Animate each still into real AI video (Replicate Wan I2V, Runway fallback)."""
    token = os.environ.get("REPLICATE_API_TOKEN") or ""
    out: list[dict[str, Any]] = []
    with httpx.Client(timeout=httpx.Timeout(300.0, connect=20.0), follow_redirects=True) as client:
        for item in frames:
            shot_n = int(item["shot"])
            label = str(item["label"]).lower()
            dest = frames_dir / f"shot_{shot_n:02d}_{label}.mp4"
            still = Path(item["frame"])
            print(f"[video] shot {shot_n} {item['label']}", flush=True)
            used = None
            last_err = None
            if dest.exists() and dest.stat().st_size > 50_000:
                used = "cached_video"
            else:
                prompt = (
                    f"{item['prompt']} Animate as continuous cinematic video with natural motion, "
                    "camera drift, cloth/wind movement, sacred mythological atmosphere, no text."
                )
                if token:
                    try:
                        image_url = _replicate_upload_image(client, token, still)
                        _replicate_wan_i2v(
                            client, token, image_url=image_url, prompt=prompt, out_path=dest
                        )
                        used = "replicate:wan-2.2-i2v-fast"
                    except Exception as exc:  # noqa: BLE001
                        last_err = f"replicate: {exc}"
                        print(f"  replicate failed: {exc}", flush=True)
                if used is None and "runway" in available_video_backends():
                    try:
                        data_uri = (
                            "data:image/png;base64,"
                            + base64.b64encode(still.read_bytes()).decode("ascii")
                        )
                        generate_video(
                            prompt,
                            duration_sec=5,
                            image_url=data_uri,
                            out_path=dest,
                            prefer="runway",
                        )
                        used = "runway:i2v:gen4.5"
                    except Exception as exc:  # noqa: BLE001
                        last_err = f"{last_err} | runway: {exc}" if last_err else f"runway: {exc}"
                        print(f"  runway failed: {exc}", flush=True)
            if used is None or not dest.exists() or dest.stat().st_size < 50_000:
                print(f"  SKIP (no AI video): {last_err}", flush=True)
                out.append(item)
                continue
            merged = {
                **item,
                "clip": str(dest),
                "visual_kind": "live_video",
                "provider": used,
            }
            (frames_dir / f"shot_{shot_n:02d}_video_card.json").write_text(json.dumps(merged, indent=2))
            out.append(merged)
            print(f"  ok {used} {dest.stat().st_size}", flush=True)
            time.sleep(2)
    return out


def generate_voiceover(root: Path) -> Path:
    key = os.environ.get("ELEVENLABS_API_KEY") or ""
    # Premade Liam — library voices need paid API
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID_PREMADE") or "TX3LPaxmHKxFdv7VOQHJ"
    dest = root / "voiceover.mp3"
    if dest.exists() and dest.stat().st_size > 1000:
        print("[vo] cached", dest, flush=True)
        return dest
    print("[vo] generating…", flush=True)
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": key,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
            json={
                "text": VO_SCRIPT,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.75,
                    "style": 0.3,
                    "use_speaker_boost": True,
                },
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"elevenlabs {r.status_code}: {r.text[:400]}")
        dest.write_bytes(r.content)
    print("[vo]", dest.stat().st_size, flush=True)
    return dest


def generate_music(root: Path, duration_sec: float) -> Path:
    token = os.environ.get("REPLICATE_API_TOKEN") or ""
    dest = root / "music_bed.mp3"
    if dest.exists() and dest.stat().st_size > 1000:
        print("[music] cached", dest, flush=True)
        return dest
    dur = int(max(15, min(90, round(duration_sec + 2))))
    prompt = (
        "Sacred Indian mythological instrumental, soft bansuri and tanpura drone, "
        "devotional and cinematic, no vocals, temple atmosphere, emotional and solemn, "
        f"{dur} seconds, clean ending"
    )
    print(f"[music] generating {dur}s…", flush=True)
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=20.0), follow_redirects=True) as client:
        r = client.post(
            "https://api.replicate.com/v1/models/stability-ai/stable-audio-2.5/predictions",
            headers={
                "Authorization": f"Bearer {token}",
                "Prefer": "wait=60",
                "Content-Type": "application/json",
            },
            json={"input": {"prompt": prompt, "duration": dur, "steps": 8, "cfg_scale": 1}},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"music submit {r.status_code}: {r.text[:400]}")
        data = r.json()
        status = data.get("status")
        get_url = (data.get("urls") or {}).get("get")
        while status in {"starting", "processing"} and get_url:
            time.sleep(3)
            data = client.get(get_url, headers={"Authorization": f"Bearer {token}"}).json()
            status = data.get("status")
            print("  music", status, flush=True)
        if status != "succeeded":
            raise RuntimeError(f"music failed: {data}")
        out = data.get("output")
        url = out[0] if isinstance(out, list) else out
        dest.write_bytes(client.get(str(url)).content)
    print("[music]", dest.stat().st_size, flush=True)
    return dest


def _probe_duration(path: Path, ffmpeg: str) -> float:
    # ffmpeg -i prints duration to stderr
    proc = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr or "")
    if not m:
        return 45.0
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def _allocate_timings(total: float) -> list[dict[str, Any]]:
    weights = [float(s["weight"]) for s in SHOTS]
    wsum = sum(weights) or 1.0
    t = 0.0
    timed: list[dict[str, Any]] = []
    for i, shot in enumerate(SHOTS):
        dur = total * (weights[i] / wsum)
        if i == len(SHOTS) - 1:
            dur = max(0.4, total - t)
        item = {**shot, "t0": round(t, 3), "t1": round(t + dur, 3)}
        timed.append(item)
        t += dur
    return timed


def render_reel(
    root: Path,
    frames: list[dict[str, Any]],
    timed: list[dict[str, Any]],
    vo: Path,
    music: Path,
    total: float,
) -> Path:
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg missing")
    width, height, fps = 1080, 1920, 30
    tmp = root / "_render_tmp"
    tmp.mkdir(exist_ok=True)
    concat_lines: list[str] = []
    by_shot = {int(f["shot"]): f for f in frames}

    for shot in timed:
        shot_n = int(shot["shot"])
        meta = by_shot[shot_n]
        duration = max(0.35, float(shot["t1"]) - float(shot["t0"]))
        clip_out = tmp / f"shot_{shot_n:02d}.mp4"
        text = shot.get("text")
        draw = ""
        if text:
            escaped = _escape_drawtext(str(text))
            draw = (
                f",drawtext=fontfile={_fontfile()}:text='{escaped}':fontsize=54:"
                "fontcolor=white:borderw=3:bordercolor=black@0.8:box=1:boxcolor=black@0.45:"
                "boxborderw=18:x=(w-text_w)/2:y=h*0.78"
            )
        video_src = Path(meta["clip"]) if meta.get("clip") and Path(meta["clip"]).exists() else None
        if video_src is not None:
            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps={fps},format=yuv420p{draw}"
            )
            cmd = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stream_loop",
                "-1",
                "-i",
                str(video_src),
                "-t",
                f"{duration:.3f}",
                "-vf",
                vf,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                str(clip_out),
            ]
        else:
            frame = Path(meta["frame"])
            vf = (
                f"scale={int(width*1.08)}:{int(height*1.08)},"
                f"crop={width}:{height},fps={fps},format=yuv420p{draw}"
            )
            cmd = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(frame),
                "-vf",
                vf,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                str(clip_out),
            ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr[-1500:] or f"render shot {shot_n} failed")
        # Paths in concat lists are relative to the list file's directory.
        concat_lines.append(f"file '{clip_out.name}'")

    list_file = tmp / "concat.txt"
    list_file.write_text("\n".join(concat_lines) + "\n")
    silent = root / "barbarik_silent.mp4"
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(silent),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1500:] or "concat failed")

    mix = root / "audio_mix.m4a"
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(music),
            "-i",
            str(vo),
            "-filter_complex",
            f"[0:a]atrim=0:{total:.3f},afade=t=in:st=0:d=0.8,afade=t=out:st={max(0.5,total-1.2):.3f}:d=1.0,volume=0.28[bed];"
            f"[1:a]volume=1.2,afade=t=out:st={max(0.5,total-0.8):.3f}:d=0.7[vo];"
            "[bed][vo]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[a]",
            "-map",
            "[a]",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(mix),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1500:] or "audio mix failed")

    final = root / "barbarik_khatu_shyam.mp4"
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(silent),
            "-i",
            str(mix),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(final),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1500:] or "mux failed")
    return final


def main() -> None:
    _load_dotenv()
    root = _out_root()
    frames_dir = root / "frames"
    (root / "caption.txt").write_text(CAPTION + "\n" + " ".join(HASHTAGS) + "\n")
    (root / "script.txt").write_text(VO_SCRIPT + "\n")

    frames = generate_stills(frames_dir)
    frames = generate_clips(frames_dir, frames)

    vo = generate_voiceover(root)
    ffmpeg = resolve_ffmpeg() or "ffmpeg"
    total = _probe_duration(vo, ffmpeg)
    print(f"[timing] VO duration={total:.2f}s", flush=True)
    timed = _allocate_timings(total)
    music = generate_music(root, total)
    final = render_reel(root, frames, timed, vo, music, total)

    package = {
        "reel": CONTENT_ID,
        "hook": HOOK,
        "punchline": PUNCHLINE,
        "caption": CAPTION,
        "hashtags": HASHTAGS,
        "script": VO_SCRIPT,
        "shots": timed,
        "frames": frames,
        "visual_kind": "live_video" if any(f.get("clip") for f in frames) else "live_api",
        "duration_sec": total,
        "render_uri": str(final),
        "audio": {"voiceover": str(vo), "music": str(music)},
    }
    (root / "reel_package.json").write_text(json.dumps(package, indent=2, default=str))
    print("DONE", final, final.stat().st_size, flush=True)


if __name__ == "__main__":
    main()
