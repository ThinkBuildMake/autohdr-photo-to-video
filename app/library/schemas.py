"""Library request and response shapes."""

from pydantic import ConfigDict

from app.shared.types import CamelModel, Song, Style, StyleSummary


class StyleCreate(CamelModel):
    """A style holds text and a song only (FR-3.6): unknown fields, such as videoUrl, are
    dropped and never stored."""

    model_config = ConfigDict(extra="ignore")

    name: str
    author_name: str
    style_text: str
    song_id: str
    song_offset_s: float = 0.0
    fps: int = 30
    demo_photoshoot_id: str | None = None


class StyleUpdate(CamelModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    style_text: str | None = None
    song_id: str | None = None
    song_offset_s: float | None = None
    fps: int | None = None


class StyleList(CamelModel):
    styles: list[StyleSummary]


class StyleDetail(CamelModel):
    style: Style
    reference_video_url: str | None


class SongList(CamelModel):
    songs: list[Song]


class StyleOne(CamelModel):
    style: Style
