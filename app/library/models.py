"""Library tables: songs, styles."""

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import NOW_UTC, Base


class Song(Base):
    __tablename__ = "songs"
    __table_args__ = (
        CheckConstraint("licence_code in ('BY-NC','BY-NC-SA')", name="ck_songs_licence"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    artist: Mapped[str]
    licence_code: Mapped[str]
    source_url: Mapped[str]
    file_key: Mapped[str]
    duration_s: Mapped[float] = mapped_column(REAL)
    created_at: Mapped[str] = mapped_column(server_default=NOW_UTC)


class Style(Base):
    __tablename__ = "styles"
    __table_args__ = (
        CheckConstraint("fps in (24, 30)", name="ck_styles_fps"),
        CheckConstraint("length(style_text) between 1 and 4000", name="ck_styles_style_text_len"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    author_name: Mapped[str]
    style_text: Mapped[str]
    song_id: Mapped[str] = mapped_column(ForeignKey("songs.id"))
    song_offset_s: Mapped[float] = mapped_column(REAL, server_default=text("0"))
    fps: Mapped[int] = mapped_column(Integer, server_default=text("30"))
    demo_photoshoot_id: Mapped[str | None] = mapped_column(ForeignKey("photoshoots.id"))
    reference_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    created_at: Mapped[str] = mapped_column(server_default=NOW_UTC)
    updated_at: Mapped[str] = mapped_column(server_default=NOW_UTC)
