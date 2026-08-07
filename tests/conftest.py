from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import get_settings
from db.session import init_db, reset_engine


@pytest.fixture()
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("STORAGE_ROOT", str(storage))
    monkeypatch.setenv("PIPELINE_STUB_PROVIDERS", "true")
    get_settings.cache_clear()
    reset_engine()

    # Agents write under ./storage relative to CWD — point CWD storage at tmp via symlink-ish dirs.
    cwd_storage = Path("storage")
    for sub in ("raw", "rendered", "archive"):
        (cwd_storage / sub).mkdir(parents=True, exist_ok=True)

    init_db(url)
    yield url
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orchestration.retry.time.sleep", lambda _: None)
