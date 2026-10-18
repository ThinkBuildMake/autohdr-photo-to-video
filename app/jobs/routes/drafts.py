"""Jobs routes: drafts and the shot plan."""

from fastapi import APIRouter

from app.jobs import drafts
from app.jobs.schemas import JobCreate, JobOne, JobReplan, JobShotsUpdate

router = APIRouter()


@router.post("/jobs", status_code=201)
def create_job(body: JobCreate) -> JobOne:
    return JobOne(job=drafts.create_job(body))


@router.post("/jobs/{job_id}/plan", status_code=202)
def replan_job(job_id: str, body: JobReplan) -> JobOne:
    return JobOne(job=drafts.replan_job(job_id, body))


@router.put("/jobs/{job_id}/shots")
def update_job_shots(job_id: str, body: JobShotsUpdate) -> JobOne:
    return JobOne(job=drafts.update_job_shots(job_id, body.shots))
