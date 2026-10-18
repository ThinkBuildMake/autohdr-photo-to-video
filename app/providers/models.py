"""Providers table: provider_calls."""

from sqlalchemy import REAL, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProviderCall(Base):
    __tablename__ = "provider_calls"
    __table_args__ = (Index("ix_provider_calls_job_id", "job_id"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    model: Mapped[str]
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    job_shot_id: Mapped[str | None] = mapped_column(ForeignKey("job_shots.id"))
    attempt_id: Mapped[str | None] = mapped_column(ForeignKey("attempts.id"))
    photoshoot_id: Mapped[str | None] = mapped_column(ForeignKey("photoshoots.id"))
    provider_request_id: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default=text("'running'"))
    error_kind: Mapped[str | None]
    error_message: Mapped[str | None]
    output_seconds: Mapped[float | None] = mapped_column(REAL)
    cost_usd: Mapped[float] = mapped_column(REAL, server_default=text("0"))
    cost_source: Mapped[str] = mapped_column(server_default=text("'reported'"))
    started_at: Mapped[str]
    finished_at: Mapped[str | None]
