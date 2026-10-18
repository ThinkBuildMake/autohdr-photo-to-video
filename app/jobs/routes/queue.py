"""Jobs routes: queue and reading."""

from fastapi import APIRouter

from app.jobs import queue
from app.jobs.schemas import JobList, JobOne, VideoLinks

router = APIRouter()


@router.post("/jobs/{job_id}/submit", status_code=202)
def submit_job(job_id: str) -> JobOne:
    return JobOne(job=queue.submit_job(job_id))


@router.get("/jobs")
def list_jobs() -> JobList:
    return JobList(jobs=queue.list_jobs())


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> JobOne:
    return JobOne(job=queue.get_job(job_id))


@router.get("/jobs/{job_id}/video")
def get_video(job_id: str) -> VideoLinks:
    return VideoLinks(**queue.get_video(job_id))
