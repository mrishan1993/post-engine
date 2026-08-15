from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default=f"sqlite:///{ROOT / 'storage' / 'pipeline.db'}",
        alias="DATABASE_URL",
    )
    storage_root: Path = Field(default=ROOT / "storage", alias="STORAGE_ROOT")
    pipeline_stub_providers: bool = Field(default=True, alias="PIPELINE_STUB_PROVIDERS")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    suno_api_key: str | None = Field(default=None, alias="SUNO_API_KEY")

    # Image / video generation (wire providers when keys are present)
    fal_key: str | None = Field(default=None, alias="FAL_KEY")
    replicate_api_token: str | None = Field(default=None, alias="REPLICATE_API_TOKEN")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    midjourney_api_key: str | None = Field(default=None, alias="MIDJOURNEY_API_KEY")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    runway_api_key: str | None = Field(default=None, alias="RUNWAY_API_KEY")

    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")
    youtube_client_id: str | None = Field(default=None, alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str | None = Field(default=None, alias="YOUTUBE_CLIENT_SECRET")
    youtube_refresh_token: str | None = Field(default=None, alias="YOUTUBE_REFRESH_TOKEN")
    instagram_access_token: str | None = Field(default=None, alias="INSTAGRAM_ACCESS_TOKEN")
    instagram_user_id: str | None = Field(default=None, alias="INSTAGRAM_USER_ID")
    temp_hosting_base_url: str | None = Field(default=None, alias="TEMP_HOSTING_BASE_URL")
    alert_webhook_url: str | None = Field(default=None, alias="ALERT_WEBHOOK_URL")
    trend_stub_collectors: bool = Field(default=True, alias="TREND_STUB_COLLECTORS")
    # Used to encrypt social credential payloads at rest (never store tokens plaintext)
    credentials_key: str = Field(
        default="amp-dev-credentials-key-change-me",
        alias="AMP_CREDENTIALS_KEY",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
