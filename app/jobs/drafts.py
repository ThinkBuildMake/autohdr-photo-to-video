"""Jobs: drafts and the shot plan (createJob, replanJob, updateJobShots). Stub until S09."""

from app.errors import AppError
from app.jobs import queue, stubs
from app.jobs.schemas import JobCreate, JobReplan
from app.library import service as library
from app.photoshoots import service as photoshoots
from app.shared.enums import JobStatus
from app.shared.types import Job, PlannedShot


def create_job(body: JobCreate) -> Job:
    if not 1 <= len(body.style_text) <= 4000:
        raise AppError(400, "invalid_style", "The style text must be 1 to 4000 characters.")
    if body.style_id is not None:
        library.get_style(body.style_id)
    if body.song_id not in [song.id for song in library.list_songs()]:
        raise AppError(404, "song_not_found", f"No song with id {body.song_id}.")
    photoshoots.get_photoshoot(body.photoshoot_id)
    return stubs.stub_job().model_copy(
        update={
            "status": JobStatus.draft,
            "plan_status": "planning",
            "style_text": body.style_text,
            "purpose": body.purpose,
            "video": None,
            "submitted_at": None,
            "started_at": None,
            "finished_at": None,
            "elapsed_s": 0.0,
            "shots": [],
        }
    )


def replan_job(job_id: str, body: JobReplan) -> Job:
    job = queue.get_job(job_id)
    if body.style_text is not None and not 1 <= len(body.style_text) <= 4000:
        raise AppError(400, "invalid_style", "The style text must be 1 to 4000 characters.")
    return job.model_copy(update={"status": JobStatus.draft, "plan_status": "planning"})


def update_job_shots(job_id: str, shots: list[PlannedShot]) -> Job:
    job = queue.get_job(job_id)
    return job.model_copy(update={"status": JobStatus.draft})


def on_app_start() -> None:
    """S09 plans again any job left in planning."""
    return None
