from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings
from db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(database_url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    settings = get_settings()
    url = database_url or settings.database_url

    if _engine is None or (database_url and str(_engine.url) != database_url):
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        engine = create_engine(url, future=True, connect_args=connect_args)

        if url.startswith("sqlite"):

            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        _engine = engine
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)

    assert _engine is not None
    return _engine


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db(database_url: str | None = None) -> None:
    settings = get_settings()
    storage = Path(settings.storage_root)
    for sub in ("raw", "rendered", "archive"):
        (storage / sub).mkdir(parents=True, exist_ok=True)

    if (database_url or settings.database_url).startswith("sqlite"):
        db_path = Path(str((database_url or settings.database_url).replace("sqlite:///", "")))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session(database_url: str | None = None) -> Generator[Session, None, None]:
    get_engine(database_url)
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
