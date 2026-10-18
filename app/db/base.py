"""Engine, session and declarative base. Every connection: foreign keys on, WAL, busy timeout."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, Text, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

NOW_UTC = text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))")


class Base(DeclarativeBase):
    type_annotation_map = {str: Text}


_lock = threading.Lock()
_engine: Engine | None = None
_sessions: sessionmaker[Session] | None = None


def _set_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
    finally:
        cursor.close()


def get_engine() -> Engine:
    global _engine, _sessions
    with _lock:
        if _engine is None:
            path = Path(get_settings().DATABASE_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(
                f"sqlite:///{path}",
                connect_args={"timeout": 10, "check_same_thread": False},
            )
            event.listen(engine, "connect", _set_pragmas)
            _engine = engine
            _sessions = sessionmaker(engine, expire_on_commit=False)
        return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """One short transaction: commit on success, roll back on error."""
    get_engine()
    assert _sessions is not None
    session = _sessions()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    global _engine, _sessions
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _sessions = None
