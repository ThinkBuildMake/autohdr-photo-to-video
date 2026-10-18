"""Jobs: restart, redo and editor re-export. Stub until S11."""

from app.errors import AppError
from app.jobs import queue
from app.jobs.schemas import ExportPlan, ShotEdit, ShotEditResult
from app.shared.enums import JobStatus
from app.shared.types import Job, JobShot


def restart_job(job_id: str) -> Job:
    job = queue.get_job(job_id)
    return job.model_copy(update={"status": JobStatus.queued})


def redo_shot(job_id: str, position: int) -> Job:
    job = queue.get_job(job_id)
    _find_shot(job, position)
    return job.model_copy(update={"status": JobStatus.queued})


def edit_shot(job_id: str, position: int, body: ShotEdit) -> ShotEditResult:
    job = queue.get_job(job_id)
    shot = _find_shot(job, position)
    changes = body.model_dump(exclude_none=True)
    shot = shot.model_copy(update={**changes, "pending_change": "new_clip"})
    return ShotEditResult(shot=shot, export_plan=ExportPlan(new_clips=1, recut_only=0, removed=0))


def export_job(job_id: str) -> Job:
    job = queue.get_job(job_id)
    return job.model_copy(update={"status": JobStatus.queued})


def _find_shot(job: Job, position: int) -> JobShot:
    for shot in job.shots:
        if shot.position == position:
            return shot
    raise AppError(404, "shot_not_found", f"Job {job.id} has no shot at position {position}.")
