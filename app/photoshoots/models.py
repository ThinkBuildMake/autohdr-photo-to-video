"""Photoshoots tables: photoshoots, photos."""

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import NOW_UTC, Base


class Photoshoot(Base):
    __tablename__ = "photoshoots"

    id: Mapped[str] = mapped_column(primary_key=True)
    label: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default=text("'awaiting_upload'"))
    created_at: Mapped[str] = mapped_column(server_default=NOW_UTC)


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (
        UniqueConstraint("photoshoot_id", "position", name="uq_photos_photoshoot_position"),
        CheckConstraint("size_bytes <= 26214400", name="ck_photos_size"),
        CheckConstraint("content_type in ('image/jpeg','image/png')", name="ck_photos_type"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    photoshoot_id: Mapped[str] = mapped_column(ForeignKey("photoshoots.id"))
    position: Mapped[int] = mapped_column(Integer)
    original_name: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(Integer)
    file_key: Mapped[str]
    status: Mapped[str] = mapped_column(server_default=text("'awaiting_upload'"))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    room: Mapped[str | None]
    subject: Mapped[str | None]
