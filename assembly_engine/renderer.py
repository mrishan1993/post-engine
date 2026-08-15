from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from amp_platform.procedural_media import resolve_ffmpeg as resolve_bundled_ffmpeg
from assembly_engine.profiles import get_platform_profile
from assembly_engine.schemas import AssemblySpecification, BuiltTimeline
from config.settings import get_settings


def ffmpeg_version() -> str | None:
    binary = resolve_bundled_ffmpeg() or shutil.which("ffmpeg")
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, timeout=5, check=False
        )
        line = (proc.stdout or "").splitlines()[0] if proc.stdout else ""
        return line[:64] or "ffmpeg"
    except Exception:  # noqa: BLE001
        return "ffmpeg"


def _ffmpeg_bin() -> str | None:
    return resolve_bundled_ffmpeg() or shutil.which("ffmpeg")


def _is_decodable_media(uri: str) -> bool:
    path = Path(uri)
    if not path.exists() or path.stat().st_size < 64:
        return False
    head = path.read_bytes()[:32]
    if head.startswith(b"AMP_"):
        return False
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff"):
        return True
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    return False


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

        video_inputs = [
            c
            for c in self._collect_visual_inputs(timeline)
            if _is_decodable_media(str(c.get("storage_uri") or ""))
        ]
        audio_inputs = [
            c
            for c in self._collect_audio_inputs(timeline, spec)
            if _is_decodable_media(str(c.get("storage_uri") or ""))
        ]

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

        if not used_ffmpeg or not out_path.exists() or not _is_decodable_media(str(out_path)):
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
            used_ffmpeg = False

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
        """Multi-clip concat/mux — real media only."""
        _ = export, silences
        ffmpeg = _ffmpeg_bin()
        if not ffmpeg:
            raise RuntimeError("ffmpeg missing")

        voice = next((a for a in audio_inputs if a.get("track_type") == "voice"), None)
        music = next((a for a in audio_inputs if a.get("track_type") == "music"), None)

        with tempfile.TemporaryDirectory(prefix="amp_assemble_") as tmp:
            tmp_path = Path(tmp)
            seg_paths: list[Path] = []
            for i, visual in enumerate(video_inputs):
                start = float(visual.get("start") or 0)
                end = float(visual.get("end") or (start + 2))
                seg_dur = max(0.2, end - start)
                uri = str(visual["storage_uri"])
                seg = tmp_path / f"seg_{i:03d}.mp4"
                vf = (
                    f"scale={canvas.width}:{canvas.height}:force_original_aspect_ratio=increase,"
                    f"crop={canvas.width}:{canvas.height},fps={canvas.fps},format=yuv420p"
                )
                cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
                if visual.get("track_type") == "image" or uri.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    cmd += ["-loop", "1", "-t", f"{seg_dur:.3f}", "-i", uri]
                else:
                    cmd += ["-i", uri, "-t", f"{seg_dur:.3f}"]
                cmd += ["-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(seg)]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
                if proc.returncode != 0 or not seg.exists():
                    raise RuntimeError(proc.stderr[-800:] if proc.stderr else "segment failed")
                seg_paths.append(seg)

            if not seg_paths:
                raise RuntimeError("no visual segments")

            list_file = tmp_path / "concat.txt"
            lines = []
            for p in seg_paths:
                safe = str(p).replace("'", "'\\''")
                lines.append(f"file '{safe}'")
            list_file.write_text("\n".join(lines) + "\n")
            silent = tmp_path / "silent.mp4"
            cmd = [
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
                "-an",
                str(silent),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
            if proc.returncode != 0 or not silent.exists():
                raise RuntimeError(proc.stderr[-800:] if proc.stderr else "concat failed")

            cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent)]
            audio_idx: list[int] = []
            if voice and _is_decodable_media(str(voice["storage_uri"])):
                cmd += ["-i", str(voice["storage_uri"])]
                audio_idx.append(1)
            if music and _is_decodable_media(str(music["storage_uri"])):
                cmd += ["-i", str(music["storage_uri"])]
                audio_idx.append(2 if voice else 1)

            if len(audio_idx) == 1:
                cmd += ["-map", "0:v:0", "-map", f"{audio_idx[0]}:a:0?", "-c:v", "copy", "-c:a", "aac"]
            elif len(audio_idx) >= 2:
                bed = float(ducking.get("bed_db") or -12)
                filt = (
                    f"[{audio_idx[0]}:a]volume=1.0[va];"
                    f"[{audio_idx[1]}:a]volume={10 ** (bed / 20):.4f}[ma];"
                    f"[va][ma]amix=inputs=2:duration=longest:dropout_transition=0[a]"
                )
                cmd += ["-filter_complex", filt, "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac"]
            else:
                cmd += ["-map", "0:v:0", "-c:v", "copy", "-an"]

            cmd += ["-t", str(duration), "-movflags", "+faststart", str(out_path)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
            if proc.returncode != 0 or not out_path.exists():
                raise RuntimeError(proc.stderr[-1000:] if proc.stderr else "ffmpeg mux failed")

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
