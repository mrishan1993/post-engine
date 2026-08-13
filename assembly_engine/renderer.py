from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from assembly_engine.profiles import get_platform_profile
from assembly_engine.schemas import AssemblySpecification, BuiltTimeline
from config.settings import get_settings


def ffmpeg_version() -> str | None:
    if not shutil.which("ffmpeg"):
        return None
    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5, check=False
        )
        line = (proc.stdout or "").splitlines()[0] if proc.stdout else ""
        return line[:64] or "ffmpeg"
    except Exception:  # noqa: BLE001
        return "ffmpeg"


class AssemblyRenderer:
    """FFmpeg backend with offline stub fallback. Upstream never sees FFmpeg syntax."""

    def render(
        self,
        *,
        assembly_id: str,
        render_id: str,
        spec: AssemblySpecification,
        timeline: BuiltTimeline,
        quality: str = "final",
        progress_cb=None,
    ) -> dict[str, Any]:
        profile_id = spec.platform_profile
        if quality == "draft":
            profile_id = "draft_v1"
        elif quality == "preview":
            profile_id = "preview_v1"
        profile = get_platform_profile(profile_id)
        canvas = profile["canvas"]
        export = profile["export"]

        settings = get_settings()
        out_dir = Path(settings.storage_root) / "rendered" / "assembly" / assembly_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{render_id}_{quality}.mp4"

        if progress_cb:
            progress_cb(10)

        video_inputs = self._collect_visual_inputs(timeline)
        audio_inputs = self._collect_audio_inputs(timeline, spec)

        if progress_cb:
            progress_cb(30)

        version = ffmpeg_version()
        used_ffmpeg = False
        if version and video_inputs:
            try:
                self._render_ffmpeg(
                    out_path=out_path,
                    video_inputs=video_inputs,
                    audio_inputs=audio_inputs,
                    canvas=canvas,
                    export=export,
                    duration=timeline.duration_sec,
                    ducking=spec.ducking.model_dump(),
                    silences=[s.model_dump() for s in spec.silences],
                )
                used_ffmpeg = True
            except Exception:  # noqa: BLE001
                used_ffmpeg = False

        if progress_cb:
            progress_cb(80)

        if not used_ffmpeg or not out_path.exists():
            self._write_stub(
                out_path=out_path,
                assembly_id=assembly_id,
                render_id=render_id,
                timeline=timeline,
                canvas=canvas,
                export=export,
                quality=quality,
                captions=spec.captions,
                overlays=spec.overlays,
                effects=spec.effects,
            )

        if progress_cb:
            progress_cb(100)

        return {
            "storage_uri": str(out_path),
            "ffmpeg_used": used_ffmpeg,
            "ffmpeg_version": version,
            "width": canvas.width,
            "height": canvas.height,
            "fps": canvas.fps,
            "duration_sec": timeline.duration_sec,
            "video_codec": export.video_codec,
            "audio_codec": export.audio_codec,
            "mime_type": "video/mp4",
            "quality": quality,
            "platform_profile": profile_id,
        }

    def _collect_visual_inputs(self, timeline: BuiltTimeline) -> list[dict[str, Any]]:
        clips = []
        for track in timeline.tracks:
            if track.type not in {"video", "image"}:
                continue
            for c in track.clips:
                uri = c.get("storage_uri")
                if uri and Path(uri).exists():
                    clips.append({**c, "track_type": track.type})
        return sorted(clips, key=lambda x: float(x.get("start") or 0))

    def _collect_audio_inputs(
        self, timeline: BuiltTimeline, spec: AssemblySpecification
    ) -> list[dict[str, Any]]:
        clips = []
        for track in timeline.tracks:
            if track.type not in {"voice", "music", "sfx", "ambience"}:
                continue
            for c in track.clips:
                uri = c.get("storage_uri")
                if uri and Path(uri).exists():
                    vol = float(c.get("volume_db") or 0)
                    if track.type == "music":
                        # Apply bed level; ducking noted for stub/filter metadata
                        vol = min(vol, float(spec.ducking.bed_db))
                    clips.append({**c, "track_type": track.type, "volume_db": vol})
        return sorted(clips, key=lambda x: float(x.get("start") or 0))

    def _render_ffmpeg(
        self,
        *,
        out_path: Path,
        video_inputs: list[dict[str, Any]],
        audio_inputs: list[dict[str, Any]],
        canvas: Any,
        export: Any,
        duration: float,
        ducking: dict[str, Any],
        silences: list[dict[str, Any]],
    ) -> None:
        """Simplified concat/mux path for V1 — real clips when FFmpeg available."""
        # Prefer first usable video/image as visual base; mix first voice+music if present
        visual = video_inputs[0]
        voice = next((a for a in audio_inputs if a.get("track_type") == "voice"), None)
        music = next((a for a in audio_inputs if a.get("track_type") == "music"), None)

        cmd = ["ffmpeg", "-y"]
        # Visual
        if visual.get("track_type") == "image" or str(visual.get("storage_uri")).endswith(
            (".png", ".jpg", ".jpeg", ".webp")
        ):
            cmd += ["-loop", "1", "-t", str(duration), "-i", str(visual["storage_uri"])]
        else:
            cmd += ["-i", str(visual["storage_uri"])]

        audio_idx = []
        if voice:
            cmd += ["-i", str(voice["storage_uri"])]
            audio_idx.append(1)
        if music:
            cmd += ["-i", str(music["storage_uri"])]
            audio_idx.append(2 if voice else 1)

        # Scale/pad to canvas
        vf = f"scale={canvas.width}:{canvas.height}:force_original_aspect_ratio=increase,crop={canvas.width}:{canvas.height},fps={canvas.fps},format=yuv420p"
        cmd += ["-vf", vf]

        if len(audio_idx) == 1:
            cmd += ["-map", "0:v:0", "-map", f"{audio_idx[0]}:a:0?"]
        elif len(audio_idx) >= 2:
            # Mix voice + ducked music
            duck = float(ducking.get("target_db") or -20)
            bed = float(ducking.get("bed_db") or -12)
            filter = (
                f"[{audio_idx[0]}:a]volume=1.0[va];"
                f"[{audio_idx[1]}:a]volume={10 ** (bed / 20):.4f}[ma];"
                f"[va][ma]amix=inputs=2:duration=longest:dropout_transition=0[a]"
            )
            # Note: full sidechain duck is V2; V1 uses static bed level
            _ = duck
            cmd += ["-filter_complex", filter, "-map", "0:v:0", "-map", "[a]"]
        else:
            cmd += ["-map", "0:v:0", "-an"]

        cmd += [
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-t",
            str(duration),
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0 or not out_path.exists():
            raise RuntimeError(proc.stderr[-1000:] if proc.stderr else "ffmpeg failed")

    def _write_stub(
        self,
        *,
        out_path: Path,
        assembly_id: str,
        render_id: str,
        timeline: BuiltTimeline,
        canvas: Any,
        export: Any,
        quality: str,
        captions: list[Any],
        overlays: list[Any],
        effects: list[Any],
    ) -> None:
        payload = {
            "stub": True,
            "assembly_id": assembly_id,
            "render_id": render_id,
            "quality": quality,
            "width": canvas.width,
            "height": canvas.height,
            "fps": canvas.fps,
            "duration_sec": timeline.duration_sec,
            "video_codec": export.video_codec,
            "audio_codec": export.audio_codec,
            "mime_type": "video/mp4",
            "tracks": [
                {"type": t.type, "id": t.id, "clip_count": len(t.clips)} for t in timeline.tracks
            ],
            "captions": [c.model_dump() if hasattr(c, "model_dump") else c for c in captions],
            "overlays": [o.model_dump() if hasattr(o, "model_dump") else o for o in overlays],
            "effects": [e.model_dump() if hasattr(e, "model_dump") else e for e in effects],
            "silences": [s.model_dump() for s in timeline.silences],
            "ducking": timeline.ducking.model_dump(),
        }
        out_path.write_bytes(b"AMP_ASSEMBLY_STUB\n" + json.dumps(payload, indent=2).encode("utf-8"))
        out_path.with_suffix(".meta.json").write_text(json.dumps(payload), encoding="utf-8")
