"""Page: Jobs (GET /jobs)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.jobs import queue
from app.web import jobs_view
from app.web.templating import templates

router = APIRouter()


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request):
    return templates.TemplateResponse(
        request, "jobs.html", {"jobs": queue.list_jobs(), "view": jobs_view}
    )
