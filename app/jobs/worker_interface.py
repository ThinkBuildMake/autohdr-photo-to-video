"""Jobs interface for the worker (ARCHITECTURE: Jobs, Interface for other modules).

Every function is one short transaction that starts with a write, so concurrent worker threads
are serialised by SQLite's write lock. Shot and attempt writes live in shot_writes.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.db.base import session_scope
from app.jobs import shot_writes
from app.jobs.errors import JobNotFound, JobNotRunning
from app.jobs.models import Attempt, Job, JobShot
from app.jobs.shot_writes import (
    finish_attempt,
    set_shot_photo,
    set_shot_result,
    set_shot_state,
    start_attempt,
)
from app.library import service as library
from app.library.models import Song
from app.library.service import StyleNotFound
from app.providers.models import ProviderCall
from app.shared import types
from app.shared.enums import StopReason

__all__ = [
    "RUN_BUDGET",
    "RecoveredClip",
    "claim_next_job",
    "cut_plan",
    "finish_attempt",
    "finish_job",
    "recover_interrupted",
    "run_context",
    "set_shot_photo",
    "set_shot_result",
    "set_shot_state",
    "start_attempt",
    "stop_job",
]

RUN_BUDGET = timedelta(minutes=30)
CUSTOM_STYLE = "Custom style"
_UNFINISHED = ("pending", "editing", "generating", "checking")
_VIDEO_KEYS = ("key", "duration_s", "width", "height", "fps")


def _total_cost(job_id: str):
    return (
        select(func.coalesce(func.sum(ProviderCall.cost_usd), 0))
        .where(ProviderCall.job_id == job_id)
        .scalar_subquery()
    )


def _lock_running_job(session, job_id: str, **values) -> None:
    """Conditional write on a running job: JobNotFound if absent, JobNotRunning if not running."""
    result = session.execute(
        update(Job).where(Job.id == job_id, Job.status == "running").values(**values)
    )
    if result.rowcount == 0:
        if session.get(Job, job_id) is None:
            raise JobNotFound(job_id)
        raise JobNotRunning(job_id)


def _stop(session, job_id: str, stop_reason: str, now: str) -> None:
    _lock_running_job(
        session,
        job_id,
        status="stopped",
        stop_reason=stop_reason,
        finished_at=now,
        total_cost_usd=_total_cost(job_id),
    )
    unfinished = select(JobShot.id).where(JobShot.job_id == job_id, JobShot.status.in_(_UNFINISHED))
    session.execute(
        update(Attempt)
        .where(Attempt.job_shot_id.in_(unfinished), Attempt.status == "running")
        .values(status="error", error="job_stopped", finished_at=now)
    )
    session.execute(
        update(JobShot)
        .where(JobShot.job_id == job_id, JobShot.status.in_(_UNFINISHED))
        .values(
            status="failed",
            failure_reason="job_stopped",
            status_detail="The job stopped before this shot finished.",
            updated_at=now,
        )
    )


def stop_job(job_id: str, stop_reason: str) -> None:
    if stop_reason not in {r.value for r in StopReason}:
        raise ValueError(f"Unknown stop reason {stop_reason}")
    with session_scope() as session:
        _stop(session, job_id, stop_reason, shot_writes.iso(shot_writes.now_utc()))


def recover_interrupted() -> None:
    with session_scope() as session:
        now = shot_writes.iso(shot_writes.now_utc())
        session.execute(
            update(Attempt)
            .where(Attempt.status == "running")
            .values(status="error", error="worker_restarted", finished_at=now)
        )
        for job_id in session.scalars(select(Job.id).where(Job.status == "running")).all():
            _stop(session, job_id, "worker_restarted", now)


def finish_job(
    job_id: str, status: str, stop_reason: str | None = None, video: dict | None = None
) -> None:
    if status == "stopped":
        stop_job(job_id, stop_reason)
        return
    if status not in ("ready", "ready_with_failures"):
        raise ValueError(f"A job cannot finish as {status}")
    if video is None or any(key not in video for key in _VIDEO_KEYS):
        raise ValueError("A finished job needs a video with key, duration_s, width, height, fps")
    with session_scope() as session:
        now = shot_writes.iso(shot_writes.now_utc())
        _lock_running_job(session, job_id, id=Job.id)
        states = session.scalars(
            select(JobShot.status).where(JobShot.job_id == job_id, JobShot.removed == 0)
        ).all()
        if any(state in _UNFINISHED for state in states):
            raise ValueError("A job is not finished while a shot is still being made")
        if status == "ready" and any(state in ("failed", "skipped") for state in states):
            raise ValueError("A job with a failed or skipped shot is ready_with_failures")
        session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status=status,
                video_key=video["key"],
                video_duration_s=video["duration_s"],
                video_width=video["width"],
                video_height=video["height"],
                video_fps=video["fps"],
                video_version=Job.video_version + 1,
                finished_at=now,
                first_finished_at=func.coalesce(Job.first_finished_at, now),
                total_cost_usd=_total_cost(job_id),
            )
        )


@dataclass(frozen=True)
class CutShot:
    position: int
    status: str
    clip_key: str | None
    length_s: float
    transition: str
    transition_s: float


@dataclass(frozen=True)
class CutPlan:
    song_key: str
    song_offset_s: float
    fps: int
    video_version: int
    shots: list[CutShot]


def cut_plan(job_id: str) -> CutPlan:
    """What assembly needs: the song, fps, video version and every shot not removed, in order."""
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobNotFound(job_id)
        if job.status != "running":
            raise JobNotRunning(job_id)
        shots = session.execute(
            select(
                JobShot.position,
                JobShot.status,
                Attempt.clip_key,
                JobShot.length_s,
                JobShot.transition,
                JobShot.transition_s,
            )
            .outerjoin(Attempt, Attempt.id == JobShot.final_attempt_id)
            .where(JobShot.job_id == job_id, JobShot.removed == 0)
            .order_by(JobShot.position)
        ).all()
        return CutPlan(
            song_key=session.scalar(select(Song.file_key).where(Song.id == job.song_id)),
            song_offset_s=job.song_offset_s,
            fps=job.fps,
            video_version=job.video_version,
            shots=[CutShot(*shot) for shot in shots],
        )


def claim_next_job() -> types.Job | None:
    now = shot_writes.now_utc()
    other = aliased(Job)
    queued = aliased(Job)
    oldest = (
        select(queued.id)
        .where(queued.status == "queued")
        .order_by(queued.submitted_at, queued.created_at, queued.id)
        .limit(1)
        .scalar_subquery()
    )
    claim = (
        update(Job)
        .where(Job.id == oldest, ~exists().where(other.status == "running"))
        .values(
            status="running",
            started_at=shot_writes.iso(now),
            deadline_at=shot_writes.iso(now + RUN_BUDGET),
            finished_at=None,
            stop_reason=None,
        )
        .returning(Job.id)
    )
    try:
        with session_scope() as session:
            job_id = session.execute(claim).scalar()
    except IntegrityError:
        return None
    return None if job_id is None else _claimed_job(job_id, now)


def _style_name(style_id: str | None) -> str:
    if style_id is None:
        return CUSTOM_STYLE
    try:
        return library.get_style(style_id).name or CUSTOM_STYLE
    except StyleNotFound:
        return CUSTOM_STYLE


def _song_credit(song_id: str) -> str:
    return next((s.credit for s in library.list_songs() if s.id == song_id), "")


def _shot(session, row: JobShot) -> types.JobShot:
    attempts = session.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(Attempt.job_shot_id == row.id, Attempt.round == row.round)
    )
    return types.JobShot(
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
        removed=False,
        pending_change="new_clip" if row.needs_new_clip else "none",
        plan_note=row.plan_note or "",
        edit_status=row.edit_status,
        edit_note=row.edit_note,
        model=row.model_used or row.model,
        used_fallback=row.model_used is not None and row.model_used != row.model,
        status=row.status,
        status_detail=row.status_detail or "",
        failure_reason=row.failure_reason,
        attempts=attempts,
        clip_url=None,
    )


def _claimed_job(job_id: str, now: datetime) -> types.Job:
    """The claimed job with only the shots the worker has to make: pending and not removed."""
    with session_scope() as session:
        row = session.get(Job, job_id)
        shot_rows = session.scalars(
            select(JobShot)
            .where(JobShot.job_id == job_id, JobShot.status == "pending", JobShot.removed == 0)
            .order_by(JobShot.position)
        ).all()
        shots = [_shot(session, shot) for shot in shot_rows]
    elapsed = 0.0
    if row.submitted_at is not None:
        elapsed = max(0.0, (now - datetime.fromisoformat(row.submitted_at)).total_seconds())
    return types.Job(
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
        elapsed_s=elapsed,
        total_cost_usd=row.total_cost_usd,
        waiting_behind=None,
        shots=shots,
        video=None,
        song_credit=_song_credit(row.song_id),
    )


@dataclass(frozen=True)
class RecoveredClip:
    """A clip the provider finished for an interrupted attempt, collected at startup."""

    key: str
    model: str
    requested_s: float


@dataclass(frozen=True)
class RunContext:
    round_no: int
    earlier: list[tuple[str, str | None]]
    recovered: RecoveredClip | None = None


def run_context(job_shot_id: str) -> RunContext:
    """Current round and ordered attempt outcomes, scoped to this shot alone."""
    with session_scope() as session:
        shot = session.get(JobShot, job_shot_id)
        if shot is None:
            raise LookupError(f"No shot with id {job_shot_id}")
        attempts = session.scalars(
            select(Attempt)
            .where(Attempt.job_shot_id == shot.id, Attempt.round == shot.round)
            .order_by(Attempt.attempt_no)
        ).all()
        earlier = []
        for attempt in attempts:
            kind = attempt.status
            if attempt.error:
                kind = attempt.error.split(":", 1)[0]
                if ": check:" in attempt.error or ": check failed" in attempt.error:
                    kind = f"check_error:{kind}"
            earlier.append((attempt.model, kind))
        # Offered until a later attempt records its key; that attempt still runs the normal check.
        used = set(session.scalars(select(Attempt.clip_key).where(Attempt.clip_key.is_not(None))))
        found = session.execute(
            select(ProviderCall.id, Attempt.model, Attempt.requested_s)
            .join(Attempt, Attempt.id == ProviderCall.attempt_id)
            .where(
                Attempt.job_shot_id == shot.id,
                Attempt.status == "error",
                ProviderCall.kind == "generate_clip",
                ProviderCall.status == "ok",
            )
            .order_by(ProviderCall.finished_at.desc())
        ).all()
        recovered = next(
            (
                RecoveredClip(f"clips/recovered/{call_id}.mp4", model, requested_s)
                for call_id, model, requested_s in found
                if f"clips/recovered/{call_id}.mp4" not in used
            ),
            None,
        )
        return RunContext(shot.round, earlier, recovered)
