"""Comparison table: cut_checks."""

from sqlalchemy import REAL, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import NOW_UTC, Base


class CutCheck(Base):
    __tablename__ = "cut_checks"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    expected_s: Mapped[float] = mapped_column(REAL)
    detected_s: Mapped[float | None] = mapped_column(REAL)
    error_s: Mapped[float | None] = mapped_column(REAL)
    transition: Mapped[str]
    checked_at: Mapped[str] = mapped_column(server_default=NOW_UTC)
