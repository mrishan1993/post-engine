from __future__ import annotations

from providers.base_provider import Provider


class ImageProvider(Provider):
    def health_check(self) -> bool:
        return True

    def generate(self, prompt: str, output_dir: str) -> str:
        raise NotImplementedError


class StubImageProvider(ImageProvider):
    def generate(self, prompt: str, output_dir: str) -> str:
        self.last_call_cost = 0.0
        return f"{output_dir.rstrip('/')}/stub_image.png"
