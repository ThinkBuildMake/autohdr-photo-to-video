"""Rows the Library tests need: songs, and photoshoot/job rows as foreign-key targets."""

import uuid

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db
from app.library import stubs
from app.library.models import Song, Style

SOURCE_URL = "https://example.com/music/track-a"


def add_song(
    title="Track A", artist="Artist A", licence="BY-NC", source_url=SOURCE_URL, song_id=None
) -> str:
    init_db()
    song_id = song_id or str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            Song(
                id=song_id,
                title=title,
                artist=artist,
                licence_code=licence,
                source_url=source_url,
                file_key=f"songs/{song_id}.mp3",
                duration_s=95.0,
            )
        )
    return song_id


def _add_photoshoot(session, photoshoot_id: str) -> None:
    session.execute(
        text("insert or ignore into photoshoots (id, label) values (:i, 'Test shoot')"),
        {"i": photoshoot_id},
    )


def _add_job(session, job_id, photoshoot_id, song_id, style_id=None, style_text="t") -> None:
    session.execute(
        text(
            "insert into jobs (id, style_id, style_text, photoshoot_id, song_id, song_offset_s,"
            " fps) values (:i, :st, :t, :p, :s, 0, 30)"
        ),
        {"i": job_id, "st": style_id, "t": style_text, "p": photoshoot_id, "s": song_id},
    )


def add_job_row(song_id, style_id=None, style_text="t", job_id=None) -> str:
    """Test-only raw insert of a photoshoot and a job, to give Library a foreign-key target."""
    init_db()
    job_id = job_id or str(uuid.uuid4())
    photoshoot_id = str(uuid.uuid4())
    with session_scope() as session:
        _add_photoshoot(session, photoshoot_id)
        _add_job(session, job_id, photoshoot_id, song_id, style_id, style_text)
    return job_id


@pytest.fixture
def stub_presets():
    """The stub song, demo photoshoot, reference job and two preset styles, with fixed ids."""
    init_db()
    song = stubs.STUB_SONG
    with session_scope() as session:
        session.add(
            Song(
                id=song.id,
                title=song.title,
                artist=song.artist,
                licence_code=song.licence_code,
                source_url=song.source_url,
                file_key="songs/stub.mp3",
                duration_s=song.duration_s,
            )
        )
        session.flush()
        _add_photoshoot(session, stubs.STUB_DEMO_PHOTOSHOOT_ID)
        _add_job(
            session,
            stubs.STUB_REFERENCE_JOB_ID,
            stubs.STUB_DEMO_PHOTOSHOOT_ID,
            song.id,
        )
        session.flush()
        for style in stubs.STUB_STYLES:
            session.add(
                Style(
                    id=style.id,
                    name=style.name,
                    author_name=style.author_name,
                    style_text=style.style_text,
                    song_id=song.id,
                    song_offset_s=style.song_offset_s,
                    fps=style.fps,
                    demo_photoshoot_id=style.demo_photoshoot_id,
                    reference_job_id=style.reference_job_id,
                )
            )
