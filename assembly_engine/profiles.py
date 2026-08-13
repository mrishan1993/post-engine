from __future__ import annotations

from typing import Any

from assembly_engine.schemas import CanvasSpec, ExportSpec


PLATFORM_PROFILES: dict[str, dict[str, Any]] = {
    "instagram_reels_v1": {
        "id": "instagram_reels_v1",
        "platform": "instagram_reels",
        "canvas": CanvasSpec(width=1080, height=1920, fps=30, aspect_ratio="9:16"),
        "safe_zone": {"top": 180, "bottom": 300, "left": 80, "right": 80},
        "export": ExportSpec(
            format="mp4",
            video_codec="h264",
            audio_codec="aac",
            resolution="1080x1920",
            fps=30,
            audio_sample_rate=48000,
        ),
        "target_lufs": -14,
    },
    "youtube_shorts_v1": {
        "id": "youtube_shorts_v1",
        "platform": "youtube_shorts",
        "canvas": CanvasSpec(width=1080, height=1920, fps=30, aspect_ratio="9:16"),
        "safe_zone": {"top": 120, "bottom": 220, "left": 60, "right": 60},
        "export": ExportSpec(
            format="mp4",
            video_codec="h264",
            audio_codec="aac",
            resolution="1080x1920",
            fps=30,
            audio_sample_rate=48000,
        ),
        "target_lufs": -14,
    },
    "tiktok_v1": {
        "id": "tiktok_v1",
        "platform": "tiktok",
        "canvas": CanvasSpec(width=1080, height=1920, fps=30, aspect_ratio="9:16"),
        "safe_zone": {"top": 200, "bottom": 280, "left": 70, "right": 70},
        "export": ExportSpec(
            format="mp4",
            video_codec="h264",
            audio_codec="aac",
            resolution="1080x1920",
            fps=30,
            audio_sample_rate=48000,
        ),
        "target_lufs": -12,
    },
    "preview_v1": {
        "id": "preview_v1",
        "platform": "preview",
        "canvas": CanvasSpec(width=540, height=960, fps=24, aspect_ratio="9:16"),
        "safe_zone": {"top": 90, "bottom": 150, "left": 40, "right": 40},
        "export": ExportSpec(
            format="mp4",
            video_codec="h264",
            audio_codec="aac",
            resolution="540x960",
            fps=24,
            audio_sample_rate=44100,
        ),
        "target_lufs": -14,
    },
    "draft_v1": {
        "id": "draft_v1",
        "platform": "draft",
        "canvas": CanvasSpec(width=360, height=640, fps=15, aspect_ratio="9:16"),
        "safe_zone": {"top": 60, "bottom": 100, "left": 20, "right": 20},
        "export": ExportSpec(
            format="mp4",
            video_codec="h264",
            audio_codec="aac",
            resolution="360x640",
            fps=15,
            audio_sample_rate=44100,
        ),
        "target_lufs": -14,
    },
}

CAPTION_STYLES: dict[str, dict[str, Any]] = {
    "minimal": {"font_size": 48, "weight": "regular", "highlight": False},
    "bold": {"font_size": 64, "weight": "bold", "highlight": False},
    "karaoke": {"font_size": 64, "weight": "bold", "highlight": True},
    "word_by_word": {"font_size": 72, "weight": "bold", "highlight": True},
    "cinematic": {"font_size": 52, "weight": "medium", "highlight": False},
    "comedy": {"font_size": 68, "weight": "black", "highlight": True},
}


def get_platform_profile(profile_id: str) -> dict[str, Any]:
    if profile_id not in PLATFORM_PROFILES:
        raise ValueError(f"unknown platform profile: {profile_id}")
    return dict(PLATFORM_PROFILES[profile_id])


def quality_to_profile(quality: str, platform: str = "instagram_reels_v1") -> str:
    if quality == "draft":
        return "draft_v1"
    if quality == "preview":
        return "preview_v1"
    return platform
