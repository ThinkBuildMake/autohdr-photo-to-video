"""Jobs: queue and reading (submitJob, listJobs, getJob, getVideo)."""

from sqlalchemy import func, select, update

from app.db.base import session_scope
from app.errors import AppError
from app.files import service as files
from app.jobs import models, reading, stubs
from app.jobs.errors import JobNotFound
from app.shared.types import Job, JobListItem


def get_job(job_id: str) -> Job:
    if job_id == stubs.STUB_JOB_ID:
        return stubs.stub_job()
    return reading.load_job(job_id)


def list_jobs() -> list[JobListItem]:
    return reading.list_jobs()


def submit_job(job_id: str) -> Job:
    with session_scope() as session:
        row = session.get(models.Job, job_id)
        if row is None:
            raise JobNotFound(job_id)
        if row.status != "draft":
            raise AppError(409, "not_draft", "Only a draft can be submitted.")
        if row.plan_status != "ready":
            raise AppError(409, "plan_not_ready", "The shot plan is not ready yet.")
        to_make = session.scalar(
            select(func.count())
            .select_from(models.JobShot)
            .where(
                models.JobShot.job_id == job_id,
                models.JobShot.photo_id.is_not(None),
                models.JobShot.removed == 0,
            )
        )
        if not to_make:
            raise AppError(
                409, "no_shots_to_make", "Every shot is skipped: there is nothing to make."
            )
        now = reading.now_utc()
        queued = session.execute(
            update(models.Job)
            .where(models.Job.id == job_id, models.Job.status == "draft")
            .values(
                status="queued",
                submitted_at=now,
                first_submitted_at=func.coalesce(models.Job.first_submitted_at, now),
            )
        )
        if queued.rowcount == 0:
            raise AppError(409, "not_draft", "Only a draft can be submitted.")
        session.execute(
            update(models.JobShot)
            .where(models.JobShot.job_id == job_id, models.JobShot.photo_id.is_(None))
            .values(
                status="skipped",
                failure_reason="no_photo",
                status_detail="Skipped: no photo of this room.",
                updated_at=now,
            )
        )
    return reading.load_job(job_id)


def get_video(job_id: str) -> dict:
    if job_id == stubs.STUB_JOB_ID:
        return stubs.stub_video_links()
    with session_scope() as session:
        row = session.get(models.Job, job_id)
        if row is None:
            raise JobNotFound(job_id)
        key, version, duration = row.video_key, row.video_version, row.video_duration_s
    if not key:
        raise AppError(409, "no_video", "This job has no video yet.")
    return {
        "url": files.presign_download(key),
        "download_url": files.presign_download(
            key, as_attachment=True, filename=f"video-{job_id[:8]}-v{version}.mp4"
        ),
        "duration_s": duration or 0.0,
    }
