"""Page: one job (GET /jobs/{job_id})."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.errors import AppError
from app.jobs import queue
from app.web.templating import templates

router = APIRouter()


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(request: Request, job_id: str):
    try:
        job = queue.get_job(job_id)
    except AppError as exc:
        return templates.TemplateResponse(
            request, "job.html", {"job": None, "error": exc.message}, status_code=exc.status_code
        )
    return templates.TemplateResponse(request, "job.html", {"job": job, "error": None})
