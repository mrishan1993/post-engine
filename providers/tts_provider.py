from __future__ import annotations

import wave
from pathlib import Path

from providers.base_provider import Provider


class TTSProvider(Provider):
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


class StubTTSProvider(TTSProvider):
    def generate(
        self,
        script: str,
        style_prompt: str,
        voice_id: str | None,
        output_dir: str,
    ) -> tuple[str, int]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "narration.wav"
        duration_sec = max(3, min(30, len(script.split()) // 3 or 3))
        sample_rate = 16000
        num_frames = sample_rate * duration_sec
        with wave.open(str(path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * num_frames)
        self.last_call_cost = 0.15
        return str(path), duration_sec


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self, api_key: str, default_voice_id: str | None = None):
        self.api_key = api_key
        self.default_voice_id = default_voice_id

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
            "ElevenLabsTTSProvider.generate is not wired yet. "
            "Use PIPELINE_STUB_PROVIDERS=true for local runs."
        )
