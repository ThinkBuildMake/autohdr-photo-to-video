"""Page: the editor (GET /jobs/{job_id}/edit)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.errors import AppError
from app.jobs import queue
from app.jobs.plan_rules import MOVEMENTS
from app.photoshoots import service as photoshoots
from app.shared.enums import JobStatus
from app.web.templating import templates

router = APIRouter()

# PRD pp.8-9 names, in MovementName order.
MOVEMENT_LABELS = {
    "dolly_in": "Dolly In",
    "dolly_in_timelapse": "Dolly In (timelapse)",
    "drone_top_down_descend": "Drone Top Down Descend",
    "timelapse_variant": "Timelapse Variant",
    "dolly_out": "Dolly Out",
    "slider_truck_left_to_right": "Slider Truck Left to Right",
    "slider_truck_right_to_left": "Slider Truck Right to Left",
    "parallax_orbit": "Parallax Orbit",
    "dolly_in_pan_right": "Dolly In + Pan Right",
    "crane_up": "Crane Up",
    "crane_down": "Crane Down",
    "orbit_hyperlapse": "Orbit (Hyperlapse)",
}


@router.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
def editor_page(request: Request, job_id: str):
    try:
        job = queue.get_job(job_id)
        shoot = photoshoots.get_photoshoot(job.photoshoot_id)
    except AppError as exc:
        return templates.TemplateResponse(
            request, "editor.html", {"job": None, "error": exc.message}, status_code=exc.status_code
        )
    context = {
        "job": job,
        "shoot": shoot,
        "error": None,
        "busy": job.status in (JobStatus.queued, JobStatus.running),
        "movement_labels": MOVEMENT_LABELS,
        "movement_prompts": MOVEMENTS,
    }
    return templates.TemplateResponse(request, "editor.html", context)
