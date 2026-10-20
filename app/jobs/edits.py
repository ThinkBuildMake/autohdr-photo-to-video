"""Jobs: restart, redo, editor edits and re-export (restartJob, redoShot, editShot, exportJob).

Restart, redo and export set shots back to `pending` in a new round and queue the job; the
worker makes the pending shots and re-cuts the video from every shot not removed. An edit only
marks what the next export will do; a removal alone leaves edited_at alone, and queuing a run
stamps each removed shot's edited_at with the run's submitted_at, so a shot put back reads as
re-cut only if it was left out of the last video. Every function is one transaction whose first
statement is a write on the job, so it is serialised with the worker.
"""

import json
import math

from sqlalchemy import select, update

from app.db.base import session_scope
from app.errors import AppError
from app.jobs import models, plan_rules, reading
from app.jobs.errors import JobNotFound
from app.jobs.schemas import ExportPlan, ShotEdit, ShotEditResult
from app.photoshoots import service as photoshoots
from app.providers.interface import allowed_lengths
from app.shared.types import Job, PlannedShot

# A change to any of these needs a new clip (FR-1.16; speed: INDEX amendment 8).
_NEW_CLIP_FIELDS = ("photo_id", "movement_name", "movement_prompt", "speed", "photo_edit_prompts")
_EDITABLE = (
    "room", "photo_id", "movement_name", "movement_prompt", "speed",
    "length_s", "transition", "transition_s",
)  # fmt: skip


def _lock_job(session, job_id: str) -> models.Job:
    """No-op write on the job, so the transaction holds the write lock; returns the job."""
    session.execute(update(models.Job).where(models.Job.id == job_id).values(id=models.Job.id))
    row = session.get(models.Job, job_id)
    if row is None:
        raise JobNotFound(job_id)
    return row


def _requeue(session, job_id: str, *shots_where) -> None:
    """Shots matching `shots_where` → pending in a new round; the job → queued, a new run."""
    now = reading.now_utc()
    session.execute(
        update(models.JobShot)
        .where(models.JobShot.job_id == job_id, *shots_where)
        .values(
            status="pending",
            round=models.JobShot.round + 1,
            failure_reason=None,
            status_detail=None,
            final_attempt_id=None,
            needs_new_clip=0,
            updated_at=now,
        )
    )
    session.execute(
        update(models.JobShot)
        .where(models.JobShot.job_id == job_id, models.JobShot.removed == 1)
        .values(edited_at=now)
    )
    session.execute(
        update(models.Job)
        .where(models.Job.id == job_id)
        .values(status="queued", stop_reason=None, submitted_at=now)
    )


def restart_job(job_id: str) -> Job:
    with session_scope() as session:
        if _lock_job(session, job_id).status != "stopped":
            raise AppError(409, "not_stopped", "Only a stopped job can start again.")
        _requeue(
            session,
            job_id,
            models.JobShot.status.not_in(("passed", "skipped")),
            models.JobShot.photo_id.is_not(None),
            models.JobShot.removed == 0,
        )
    return reading.load_job(job_id)


def _check_finished(status: str) -> None:
    if status in ("queued", "running"):
        raise AppError(409, "job_busy", "The job is being made; wait until it finishes.")
    if status not in ("ready", "ready_with_failures"):
        raise AppError(409, "not_finished", "Only a finished video can be changed.")


def _shot_row(session, job_id: str, position: int) -> models.JobShot:
    row = session.scalar(
        select(models.JobShot).where(
            models.JobShot.job_id == job_id, models.JobShot.position == position
        )
    )
    if row is None:
        raise AppError(404, "shot_not_found", f"Job {job_id} has no shot at position {position}.")
    return row


def redo_shot(job_id: str, position: int) -> Job:
    with session_scope() as session:
        _check_finished(_lock_job(session, job_id).status)
        shot = _shot_row(session, job_id, position)
        if shot.photo_id is None:
            raise AppError(409, "no_photo", "This shot has no photo to make a clip from.")
        if shot.removed:
            raise AppError(409, "shot_removed", "Put this shot back before redoing it.")
        _requeue(session, job_id, models.JobShot.id == shot.id)
    return reading.load_job(job_id)


def _planned(row: models.JobShot) -> PlannedShot:
    return PlannedShot(
        position=row.position,
        room=row.room,
        photo_id=row.photo_id,
        photo_edit_prompts=json.loads(row.photo_edit_prompts),
        movement_name=row.movement_name,
        movement_prompt=row.movement_prompt,
        speed=row.speed,
        model=row.model,
        length_s=row.length_s,
        transition=row.transition,
        transition_s=row.transition_s,
        plan_note=row.plan_note or "",
    )


def _clip_s(session, row: models.JobShot) -> float:
    """Length of the clip the shot has now; 0 when it has none."""
    final = session.get(models.Attempt, row.final_attempt_id) if row.final_attempt_id else None
    return final.requested_s if final is not None and final.status == "passed" else 0.0


def _export_plan(job: Job) -> ExportPlan:
    kept = [shot.pending_change for shot in job.shots if not shot.removed]
    return ExportPlan(
        new_clips=kept.count("new_clip"),
        recut_only=kept.count("recut_only"),
        removed=sum(shot.removed for shot in job.shots),
    )


def edit_shot(job_id: str, position: int, body: ShotEdit) -> ShotEditResult:
    changes = body.model_dump(exclude_none=True)
    removed = changes.pop("removed", None)
    with session_scope() as session:
        job_row = _lock_job(session, job_id)
        _check_finished(job_row.status)
        row = _shot_row(session, job_id, position)
        rooms = {photo.id: photo.room for photo in photoshoots.list_photos(job_row.photoshoot_id)}
        if rooms.get(changes.get("photo_id")):
            changes["room"] = rooms[changes["photo_id"]]
        if "movement_name" in changes and "movement_prompt" not in changes:
            changes["movement_prompt"] = plan_rules.MOVEMENTS.get(
                changes["movement_name"], row.movement_prompt
            )
        current = _planned(row)
        edited = current.model_copy(update=changes)
        problems = plan_rules.validate_plan([edited], set(rooms), math.inf, allowed_lengths)
        if problems:
            message = " ".join(p.replace("Shot 1:", f"Shot {position}:", 1) for p in problems)
            raise AppError(400, "invalid_edit", message)
        if edited != current:
            if edited.photo_id is not None and (
                any(getattr(edited, f) != getattr(current, f) for f in _NEW_CLIP_FIELDS)
                or edited.length_s + edited.transition_s > _clip_s(session, row)
            ):
                row.needs_new_clip = 1
            for field in _EDITABLE:
                setattr(row, field, getattr(edited, field))
            row.photo_edit_prompts = json.dumps(edited.photo_edit_prompts)
            row.plan_note = "changed_by_photographer"
            row.edited_at = reading.now_utc()
        if removed is not None:
            row.removed = int(removed)
    job = reading.load_job(job_id)
    shot = next(s for s in job.shots if s.position == position)
    return ShotEditResult(shot=shot, export_plan=_export_plan(job))


def export_job(job_id: str) -> Job:
    with session_scope() as session:
        job_row = _lock_job(session, job_id)
        _check_finished(job_row.status)
        shots = session.scalars(select(models.JobShot).where(models.JobShot.job_id == job_id))
        if not any(
            reading.pending_change(s, job_row.submitted_at) != "none"
            or reading.edited_since(s, job_row.submitted_at)
            or (s.removed and not reading.removed_in_run(s, job_row.submitted_at))
            for s in shots
        ):
            raise AppError(409, "nothing_to_export", "Nothing changed since the last video.")
        _requeue(
            session,
            job_id,
            models.JobShot.needs_new_clip == 1,
            models.JobShot.removed == 0,
            models.JobShot.photo_id.is_not(None),
        )
    return reading.load_job(job_id)
