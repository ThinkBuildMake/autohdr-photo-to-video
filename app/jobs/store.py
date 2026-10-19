"""Jobs store: the jobs and job_shots tables. Only Jobs writes them."""

import json
import uuid

from sqlalchemy import delete, select

from app.db.base import session_scope
from app.jobs import models
from app.jobs.errors import JobNotFound
from app.shared.types import PlannedShot


def insert_job(
    photoshoot_id: str,
    style_id: str | None,
    style_text: str,
    song_id: str,
    song_offset_s: float,
    fps: int,
    purpose: str = "video",
) -> str:
    job_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            models.Job(
                id=job_id,
                style_id=style_id,
                style_text=style_text,
                photoshoot_id=photoshoot_id,
                plan_status="planning",
                purpose=purpose,
                status="draft",
                song_id=song_id,
                song_offset_s=song_offset_s,
                fps=fps,
            )
        )
    return job_id


def _get_row(session, job_id: str) -> models.Job:
    row = session.get(models.Job, job_id)
    if row is None:
        raise JobNotFound(job_id)
    return row


def planning_inputs(job_id: str) -> dict:
    with session_scope() as session:
        row = _get_row(session, job_id)
        return {
            "style_text": row.style_text,
            "song_id": row.song_id,
            "song_offset_s": row.song_offset_s,
            "photoshoot_id": row.photoshoot_id,
            "status": row.status,
            "plan_status": row.plan_status,
        }


def replace_plan(job_id: str, shots: list[PlannedShot], notes: str | None) -> None:
    with session_scope() as session:
        row = _get_row(session, job_id)
        session.execute(delete(models.JobShot).where(models.JobShot.job_id == job_id))
        session.flush()
        for shot in shots:
            session.add(
                models.JobShot(
                    id=str(uuid.uuid4()),
                    job_id=job_id,
                    position=shot.position,
                    room=shot.room,
                    photo_id=shot.photo_id,
                    photo_edit_prompts=json.dumps(shot.photo_edit_prompts),
                    movement_name=shot.movement_name,
                    movement_prompt=shot.movement_prompt,
                    speed=shot.speed,
                    model=shot.model,
                    length_s=shot.length_s,
                    transition=shot.transition,
                    transition_s=shot.transition_s,
                    plan_note=shot.plan_note,
                )
            )
        row.plan_status = "ready"
        row.plan_notes = notes or None


def set_plan_failed(job_id: str, reason: str) -> None:
    with session_scope() as session:
        row = _get_row(session, job_id)
        session.execute(delete(models.JobShot).where(models.JobShot.job_id == job_id))
        row.plan_status = "failed"
        row.plan_notes = reason


def set_planning(job_id: str, style_text: str | None = None, song_id: str | None = None) -> None:
    with session_scope() as session:
        row = _get_row(session, job_id)
        if style_text is not None:
            row.style_text = style_text
        if song_id is not None:
            row.song_id = song_id
        row.plan_status = "planning"
        row.plan_notes = None


def jobs_left_planning() -> list[str]:
    with session_scope() as session:
        return list(
            session.scalars(
                select(models.Job.id).where(
                    models.Job.status == "draft", models.Job.plan_status == "planning"
                )
            )
        )
