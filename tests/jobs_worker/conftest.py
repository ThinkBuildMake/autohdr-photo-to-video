from datetime import UTC, datetime

import pytest

from app.jobs import shot_writes
from tests.support.library_rows import add_song
from tests.support.worker_rows import add_job, add_shoot

START = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def song():
    return add_song()


@pytest.fixture
def shoot():
    return add_shoot()


@pytest.fixture
def clock(monkeypatch):
    """A settable fixed clock: clock.now = datetime(...)."""

    class Clock:
        now = START

    monkeypatch.setattr(shot_writes, "now_utc", lambda: Clock.now)
    return Clock


@pytest.fixture
def running_job(song, shoot, clock):
    return add_job(
        shoot[0],
        song,
        status="running",
        submitted_at="2026-10-19T09:00:00.000Z",
        started_at="2026-10-19T10:00:00.000Z",
        deadline_at="2026-10-19T10:30:00.000Z",
    )
