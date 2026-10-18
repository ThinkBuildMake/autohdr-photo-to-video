"""Jobs routes: restart, redo and editor re-export."""

from fastapi import APIRouter

from app.jobs import edits
from app.jobs.schemas import JobOne, ShotEdit, ShotEditResult

router = APIRouter()


@router.post("/jobs/{job_id}/restart", status_code=202)
def restart_job(job_id: str) -> JobOne:
    return JobOne(job=edits.restart_job(job_id))


@router.patch("/jobs/{job_id}/shots/{position}")
def edit_shot(job_id: str, position: int, body: ShotEdit) -> ShotEditResult:
    return edits.edit_shot(job_id, position, body)


@router.post("/jobs/{job_id}/export", status_code=202)
def export_job(job_id: str) -> JobOne:
    return JobOne(job=edits.export_job(job_id))


@router.post("/jobs/{job_id}/shots/{position}/redo", status_code=202)
def redo_shot(job_id: str, position: int) -> JobOne:
    return JobOne(job=edits.redo_shot(job_id, position))
