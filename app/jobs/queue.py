"""Jobs: queue and reading (submitJob, listJobs, getJob, getVideo). Stub until S10."""

from app.errors import AppError
from app.jobs import stubs
from app.jobs.errors import JobNotFound
from app.shared.enums import JobStatus
from app.shared.types import Job, JobListItem


def get_job(job_id: str) -> Job:
    if job_id != stubs.STUB_JOB_ID:
        raise JobNotFound(job_id)
    return stubs.stub_job()


def list_jobs() -> list[JobListItem]:
    return [stubs.stub_list_item()]


def submit_job(job_id: str) -> Job:
    job = get_job(job_id)
    return job.model_copy(update={"status": JobStatus.queued, "video": None})


def get_video(job_id: str) -> dict:
    job = get_job(job_id)
    if job.video is None:
        raise AppError(409, "no_video", "This job has no video yet.")
    return {
        "url": job.video.url,
        "download_url": job.video.url + "?download=1",
        "duration_s": job.video.duration_s,
    }
