"""Jobs reading: turn jobs, job_shots and attempts rows into the Job and JobListItem types."""

import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.base import session_scope
from app.files import service as files
from app.jobs import models
from app.jobs.errors import JobNotFound
from app.library import service as library
from app.library.service import StyleNotFound
from app.photoshoots.models import Photoshoot
from app.shared.types import Job, JobListItem, JobShot, JobVideo

CUSTOM_STYLE = "Custom style"
_FINISHED = ("ready", "ready_with_failures", "stopped")


def now_utc() -> str:
    """The current time in the database's NOW_UTC format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def elapsed_s(status: str, submitted_at: str | None, finished_at: str | None, now: str) -> float:
    if status == "draft" or submitted_at is None:
        return 0.0
    if status in ("queued", "running"):
        end = now
    elif status in _FINISHED and finished_at is not None:
        end = finished_at
    else:
        return 0.0
    return max(
        0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(submitted_at)).total_seconds()
    )


def running_job_id(session) -> str | None:
    return session.scalar(select(models.Job.id).where(models.Job.status == "running"))


def _style_name(style_id: str | None) -> str:
    if style_id is None:
        return CUSTOM_STYLE
    try:
        return library.get_style(style_id).name or CUSTOM_STYLE
    except StyleNotFound:
        return CUSTOM_STYLE


def _song_credit(song_id: str) -> str:
    for song in library.list_songs():
        if song.id == song_id:
            return song.credit
    return ""


def edited_since(row: models.JobShot, submitted_at: str | None) -> bool:
    """The shot was edited after the job's current run was queued."""
    return row.edited_at is not None and (submitted_at is None or row.edited_at > submitted_at)


def pending_change(row: models.JobShot, submitted_at: str | None) -> str:
    """What the next re-export does with the shot; a removed shot is left out, so none."""
    if row.removed:
        return "none"
    if row.needs_new_clip:
        return "new_clip"
    return "recut_only" if edited_since(row, submitted_at) else "none"


def _shot(
    row: models.JobShot, attempts: int, clip_key: str | None, submitted_at: str | None
) -> JobShot:
    return JobShot(
        id=row.id,
        position=row.position,
        room=row.room,
        movement_name=row.movement_name,
        movement_prompt=row.movement_prompt,
        speed=row.speed,
        photo_edit_prompts=json.loads(row.photo_edit_prompts),
        length_s=row.length_s,
        transition=row.transition,
        transition_s=row.transition_s,
        photo_id=row.photo_id,
        removed=bool(row.removed),
        pending_change=pending_change(row, submitted_at),
        plan_note=row.plan_note or "",
        edit_status=row.edit_status,
        edit_note=row.edit_note,
        model=row.model_used or row.model,
        used_fallback=row.model_used is not None and row.model_used != row.model,
        status=row.status,
        status_detail=row.status_detail or "",
        failure_reason=row.failure_reason,
        attempts=attempts,
        clip_url=files.presign_download(clip_key) if clip_key else None,
    )


def load_job(job_id: str) -> Job:
    with session_scope() as session:
        row = session.get(models.Job, job_id)
        if row is None:
            raise JobNotFound(job_id)
        shot_rows = session.scalars(
            select(models.JobShot)
            .where(models.JobShot.job_id == job_id)
            .order_by(models.JobShot.position)
        ).all()
        shots = []
        for shot in shot_rows:
            count = session.scalar(
                select(func.count())
                .select_from(models.Attempt)
                .where(
                    models.Attempt.job_shot_id == shot.id,
                    models.Attempt.round == shot.round,
                )
            )
            final = (
                session.get(models.Attempt, shot.final_attempt_id)
                if shot.final_attempt_id
                else None
            )
            clip_key = final.clip_key if final is not None and final.status == "passed" else None
            shots.append((shot, count, clip_key))
        running = running_job_id(session)
    waiting_behind = running if row.status == "queued" and running != row.id else None
    video = None
    if row.video_key:
        video = JobVideo(
            url=files.presign_download(row.video_key),
            duration_s=row.video_duration_s or 0.0,
            width=row.video_width or 0,
            height=row.video_height or 0,
            version=row.video_version,
        )
    return Job(
        id=row.id,
        style_id=row.style_id,
        style_name=_style_name(row.style_id),
        photoshoot_id=row.photoshoot_id,
        purpose=row.purpose,
        style_text=row.style_text,
        plan_status=row.plan_status,
        plan_notes=row.plan_notes,
        status=row.status,
        stop_reason=row.stop_reason,
        submitted_at=row.submitted_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        elapsed_s=elapsed_s(row.status, row.submitted_at, row.finished_at, now_utc()),
        total_cost_usd=row.total_cost_usd,
        waiting_behind=waiting_behind,
        shots=[_shot(*parts, row.submitted_at) for parts in shots],
        video=video,
        song_credit=_song_credit(row.song_id),
    )


def list_jobs() -> list[JobListItem]:
    styles = {style.id: style.name for style in library.list_styles()}
    query = (
        select(models.Job, Photoshoot.label)
        .join(Photoshoot, Photoshoot.id == models.Job.photoshoot_id, isouter=True)
        .order_by(models.Job.created_at.desc(), models.Job.id.desc())
    )
    with session_scope() as session:
        rows = session.execute(query).all()
    now = now_utc()
    return [
        JobListItem(
            id=job.id,
            style_name=styles.get(job.style_id) or CUSTOM_STYLE,
            photoshoot_label=label,
            purpose=job.purpose,
            status=job.status,
            submitted_at=job.submitted_at,
            elapsed_s=elapsed_s(job.status, job.submitted_at, job.finished_at, now),
        )
        for job, label in rows
    ]
