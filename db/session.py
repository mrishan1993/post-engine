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
    for sub in ("raw", "rendered", "archive", "first_reel"):
        (storage / sub).mkdir(parents=True, exist_ok=True)

    url = database_url or settings.database_url
    if url.startswith("sqlite"):
        db_path = Path(str(url.replace("sqlite:///", "")))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
    # create_all does not ALTER existing tables — sync missing columns for local SQLite
    if url.startswith("sqlite"):
        _sync_sqlite_columns(engine)


def _sync_sqlite_columns(engine: Engine) -> None:
    """Add columns present on models but missing from existing SQLite tables.

    Needed because CLIs use create_all (not alembic) against a persistent local DB.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                # Build a conservative ADD COLUMN for SQLite
                type_sql = col.type.compile(dialect=engine.dialect)
                pieces = [f"ALTER TABLE {table.name} ADD COLUMN {col.name} {type_sql}"]
                if col.server_default is not None:
                    default = col.server_default.arg
                    if hasattr(default, "text"):
                        default = default.text
                    default_s = str(default)
                    # Quote bare string defaults
                    if default_s and not default_s.startswith("(") and not default_s.isdigit():
                        if not (default_s.startswith("'") or default_s.upper() in {"NULL", "CURRENT_TIMESTAMP"}):
                            default_s = f"'{default_s}'"
                    pieces.append(f"DEFAULT {default_s}")
                elif not col.nullable:
                    # SQLite cannot easily ADD NOT NULL without default — add nullable then rely on app defaults
                    pass
                conn.execute(text(" ".join(pieces)))


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
