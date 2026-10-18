"""Library module interface. Stub: answers from app.library.stubs until S03."""

import uuid

from app.errors import AppError
from app.library import stubs
from app.library.schemas import StyleCreate, StyleUpdate
from app.shared.types import Song, Style, StyleSummary


class StyleNotFound(AppError):
    def __init__(self, style_id: str):
        super().__init__(404, "style_not_found", f"No style with id {style_id}.")


def list_styles() -> list[StyleSummary]:
    return [stubs.summary(style) for style in stubs.STUB_STYLES]


def get_style(style_id: str) -> Style:
    for style in stubs.STUB_STYLES:
        if style.id == style_id:
            return style
    raise StyleNotFound(style_id)


def reference_video_url(style_id: str) -> str | None:
    style = get_style(style_id)
    return "/stub-media/reference.mp4" if style.reference_job_id else None


def list_songs() -> list[Song]:
    return [stubs.STUB_SONG]


def _check_text_and_fps(style_text: str | None, fps: int | None) -> None:
    if style_text is not None and not 1 <= len(style_text) <= 4000:
        raise AppError(400, "invalid_style", "The style text must be 1 to 4000 characters.")
    if fps is not None and fps not in (24, 30):
        raise AppError(400, "invalid_style", "fps must be 24 or 30.")


def _check_song(song_id: str | None) -> Song:
    for song in list_songs():
        if song_id is None or song.id == song_id:
            return song
    raise AppError(404, "song_not_found", f"No song with id {song_id}.")


def _check_name(name: str | None, own_id: str | None = None) -> None:
    for style in stubs.STUB_STYLES:
        if style.name == name and style.id != own_id:
            raise AppError(409, "name_taken", f"A style named {name} already exists.")


def create_style(body: StyleCreate) -> Style:
    _check_text_and_fps(body.style_text, body.fps)
    song = _check_song(body.song_id)
    _check_name(body.name)
    return Style(
        id=str(uuid.uuid4()),
        name=body.name,
        author_name=body.author_name,
        style_text=body.style_text,
        song=song,
        song_offset_s=body.song_offset_s,
        fps=body.fps,
        demo_photoshoot_id=body.demo_photoshoot_id,
        reference_job_id=None,
    )


def update_style(style_id: str, body: StyleUpdate) -> Style:
    style = get_style(style_id)
    _check_text_and_fps(body.style_text, body.fps)
    song = _check_song(body.song_id)
    _check_name(body.name, own_id=style_id)
    changes = body.model_dump(exclude_none=True, exclude={"song_id"})
    return style.model_copy(update={**changes, "song": song})


def set_reference_job(style_id: str, job_id: str) -> None:
    get_style(style_id)
