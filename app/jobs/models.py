"""Jobs tables: jobs, job_shots, attempts."""

from sqlalchemy import (
    REAL,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import NOW_UTC, Base
from app.shared.enums import JobStatus, ShotStatus


def _in(column: str, enum_cls) -> str:
    return f"{column} in ({', '.join(repr(m.value) for m in enum_cls)})"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JobStatus), name="ck_jobs_status"),
        CheckConstraint(
            "status <> 'stopped' or stop_reason is not null", name="ck_jobs_stop_reason"
        ),
        Index(
            "uq_jobs_one_running", "status", unique=True, sqlite_where=text("status = 'running'")
        ),
        Index("ix_jobs_status_submitted_at", "status", "submitted_at"),
        Index("ix_jobs_created_at", text("created_at DESC")),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    style_id: Mapped[str | None] = mapped_column(ForeignKey("styles.id"))
    style_text: Mapped[str]
    photoshoot_id: Mapped[str] = mapped_column(ForeignKey("photoshoots.id"))
    plan_status: Mapped[str] = mapped_column(server_default=text("'planning'"))
    plan_notes: Mapped[str | None]
    purpose: Mapped[str] = mapped_column(server_default=text("'video'"))
    status: Mapped[str] = mapped_column(server_default=text("'draft'"))
    stop_reason: Mapped[str | None]
    song_id: Mapped[str] = mapped_column(ForeignKey("songs.id"))
    song_offset_s: Mapped[float] = mapped_column(REAL)
    created_at: Mapped[str] = mapped_column(server_default=NOW_UTC)
    first_submitted_at: Mapped[str | None]
    submitted_at: Mapped[str | None]
    started_at: Mapped[str | None]
    deadline_at: Mapped[str | None]
    finished_at: Mapped[str | None]
    first_finished_at: Mapped[str | None]
    fps: Mapped[int] = mapped_column(Integer)
    video_key: Mapped[str | None]
    video_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    video_duration_s: Mapped[float | None] = mapped_column(REAL)
    video_width: Mapped[int | None] = mapped_column(Integer)
    video_height: Mapped[int | None] = mapped_column(Integer)
    video_fps: Mapped[float | None] = mapped_column(REAL)
    total_cost_usd: Mapped[float] = mapped_column(REAL, server_default=text("0"))


class JobShot(Base):
    __tablename__ = "job_shots"
    __table_args__ = (
        UniqueConstraint("job_id", "position", name="uq_job_shots_job_position"),
        CheckConstraint(_in("status", ShotStatus), name="ck_job_shots_status"),
        CheckConstraint(
            "status <> 'failed' or failure_reason is not null", name="ck_job_shots_failure_reason"
        ),
        CheckConstraint("length_s > 0", name="ck_job_shots_length"),
        CheckConstraint("transition_s >= 0", name="ck_job_shots_transition_s"),
        CheckConstraint(
            "transition = 'cut' or transition_s > 0", name="ck_job_shots_transition_len"
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    removed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    needs_new_clip: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    edited_at: Mapped[str | None]
    position: Mapped[int] = mapped_column(Integer)
    room: Mapped[str]
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("photos.id"))
    photo_edit_prompts: Mapped[str] = mapped_column(server_default=text("'[]'"))
    movement_name: Mapped[str]
    movement_prompt: Mapped[str]
    speed: Mapped[str] = mapped_column(server_default=text("'slow'"))
    model: Mapped[str]
    length_s: Mapped[float] = mapped_column(REAL)
    transition: Mapped[str] = mapped_column(server_default=text("'cut'"))
    transition_s: Mapped[float] = mapped_column(REAL, server_default=text("0"))
    plan_note: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default=text("'pending'"))
    status_detail: Mapped[str | None]
    failure_reason: Mapped[str | None]
    round: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cropped_key: Mapped[str | None]
    edited_key: Mapped[str | None]
    edit_status: Mapped[str | None]
    edit_note: Mapped[str | None]
    model_used: Mapped[str | None]
    final_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("attempts.id"))
    updated_at: Mapped[str] = mapped_column(server_default=NOW_UTC)


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint("job_shot_id", "round", "attempt_no", name="uq_attempts_shot_round_no"),
        CheckConstraint("attempt_no between 1 and 4", name="ck_attempts_attempt_no"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    job_shot_id: Mapped[str] = mapped_column(ForeignKey("job_shots.id"))
    round: Mapped[int] = mapped_column(Integer)
    attempt_no: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str]
    model: Mapped[str]
    requested_s: Mapped[float] = mapped_column(REAL)
    status: Mapped[str] = mapped_column(server_default=text("'running'"))
    clip_key: Mapped[str | None]
    check_ai_score: Mapped[float | None] = mapped_column(REAL)
    check_match_score: Mapped[float | None] = mapped_column(REAL)
    check_notes: Mapped[str | None]
    error: Mapped[str | None]
    cost_usd: Mapped[float] = mapped_column(REAL, server_default=text("0"))
    started_at: Mapped[str]
    finished_at: Mapped[str | None]
