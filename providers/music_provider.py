from __future__ import annotations

import wave
from pathlib import Path

from providers.base_provider import Provider


class MusicProvider(Provider):
    def health_check(self) -> bool:
        return True

    def generate(
        self,
        script: str,
        style_prompt: str,
        voice_id: str | None,
        output_dir: str,
    ) -> tuple[str, int]:
        raise NotImplementedError


class StubMusicProvider(MusicProvider):
    def generate(
        self,
        script: str,
        style_prompt: str,
        voice_id: str | None,
        output_dir: str,
    ) -> tuple[str, int]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "music.wav"
        duration_sec = 15
        sample_rate = 16000
        with wave.open(str(path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * (sample_rate * duration_sec))
        self.last_call_cost = 0.1
        return str(path), duration_sec


class SunoMusicProvider(MusicProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def health_check(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        script: str,
        style_prompt: str,
        voice_id: str | None,
        output_dir: str,
    ) -> tuple[str, int]:
        raise NotImplementedError(
            "SunoMusicProvider.generate is not wired yet. "
            "Use PIPELINE_STUB_PROVIDERS=true for local runs."
        )
