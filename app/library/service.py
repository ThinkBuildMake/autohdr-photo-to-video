"""Library module interface: styles and songs read and written in the database."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.base import session_scope
from app.errors import AppError
from app.library import models, stubs
from app.library.schemas import StyleCreate, StyleUpdate
from app.shared.types import Song, Style, StyleSummary


class StyleNotFound(AppError):
    def __init__(self, style_id: str):
        super().__init__(404, "style_not_found", f"No style with id {style_id}.")


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _song(row: models.Song) -> Song:
    return Song(
        id=row.id,
        title=row.title,
        artist=row.artist,
        licence_code=row.licence_code,
        source_url=row.source_url,
        duration_s=row.duration_s,
        credit=f"{row.title}, {row.artist}, CC {row.licence_code}, {row.source_url}",
    )


def _style(row: models.Style, song: models.Song) -> Style:
    return Style(
        id=row.id,
        name=row.name,
        author_name=row.author_name,
        style_text=row.style_text,
        song=_song(song),
        song_offset_s=row.song_offset_s,
        fps=row.fps,
        demo_photoshoot_id=row.demo_photoshoot_id,
        reference_job_id=row.reference_job_id,
    )


def list_styles() -> list[StyleSummary]:
    query = (
        select(models.Style, models.Song)
        .join(models.Song, models.Style.song_id == models.Song.id)
        .order_by(models.Style.created_at, models.Style.name)
    )
    with session_scope() as session:
        return [
            StyleSummary(
                id=style.id,
                name=style.name,
                author_name=style.author_name,
                style_text=style.style_text,
                song=_song(song),
                has_reference=style.reference_job_id is not None,
            )
            for style, song in session.execute(query)
        ]


def get_style(style_id: str) -> Style:
    with session_scope() as session:
        row = session.get(models.Style, style_id)
        if row is None:
            raise StyleNotFound(style_id)
        return _style(row, session.get(models.Song, row.song_id))


def reference_video_url(style_id: str) -> str | None:
    style = get_style(style_id)
    if style.reference_job_id is None:
        return None
    return stubs.reference_video_url(style.reference_job_id)


def song_preview_url(song_id: str) -> str:
    return stubs.song_preview_url(song_id)


def list_songs() -> list[Song]:
    with session_scope() as session:
        return [_song(row) for row in session.scalars(select(models.Song).order_by("title"))]


def _check_text_and_fps(style_text: str | None, fps: int | None) -> None:
    if style_text is not None and (not style_text.strip() or len(style_text) > 4000):
        raise AppError(400, "invalid_style", "The style text must be 1 to 4000 characters.")
    if fps is not None and fps not in (24, 30):
        raise AppError(400, "invalid_style", "fps must be 24 or 30.")


def _check_song(session, song_id: str) -> None:
    if session.get(models.Song, song_id) is None:
        raise AppError(404, "song_not_found", f"No song with id {song_id}.")


def _name_taken(name: str) -> AppError:
    return AppError(409, "name_taken", f"A style named {name} already exists.")


def _is_unique_name_error(error: IntegrityError) -> bool:
    return "UNIQUE constraint failed: styles.name" in str(error.orig)


def create_style(body: StyleCreate) -> Style:
    _check_text_and_fps(body.style_text, body.fps)
    if body.demo_photoshoot_id is not None:
        stubs.check_demo_photoshoot(body.demo_photoshoot_id)
    style_id = str(uuid.uuid4())
    try:
        with session_scope() as session:
            _check_song(session, body.song_id)
            session.add(
                models.Style(
                    id=style_id,
                    name=body.name,
                    author_name=body.author_name,
                    style_text=body.style_text,
                    song_id=body.song_id,
                    song_offset_s=body.song_offset_s,
                    fps=body.fps,
                    demo_photoshoot_id=body.demo_photoshoot_id,
                    reference_job_id=None,
                )
            )
    except IntegrityError as error:
        if _is_unique_name_error(error):
            raise _name_taken(body.name) from error
        if "FOREIGN KEY" in str(error.orig):
            raise AppError(
                404,
                "photoshoot_not_found",
                f"No photoshoot with id {body.demo_photoshoot_id}.",
            ) from error
        raise
    return get_style(style_id)


def update_style(style_id: str, body: StyleUpdate) -> Style:
    _check_text_and_fps(body.style_text, body.fps)
    try:
        with session_scope() as session:
            row = session.get(models.Style, style_id)
            if row is None:
                raise StyleNotFound(style_id)
            if body.song_id is not None:
                _check_song(session, body.song_id)
            for field, value in body.model_dump(exclude_none=True).items():
                setattr(row, field, value)
            row.updated_at = _now()
    except IntegrityError as error:
        if _is_unique_name_error(error):
            raise _name_taken(body.name) from error
        raise
    return get_style(style_id)


def set_reference_job(style_id: str, job_id: str, session=None) -> None:
    """With a session, writes inside the caller's transaction (Comparison checks eligibility)."""
    if session is None:
        try:
            with session_scope() as own:
                set_reference_job(style_id, job_id, own)
        except IntegrityError as error:
            raise AppError(404, "job_not_found", f"No job with id {job_id}.") from error
        return
    row = session.get(models.Style, style_id)
    if row is None:
        raise StyleNotFound(style_id)
    row.reference_job_id = job_id
    row.updated_at = _now()
