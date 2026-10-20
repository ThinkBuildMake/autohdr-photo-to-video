"""Jobs: drafts and the shot plan (createJob, replanJob, updateJobShots)."""

from app.errors import AppError
from app.jobs import plan_rules, planning, reading, store, stubs
from app.jobs.schemas import JobCreate, JobReplan
from app.library import service as library
from app.photoshoots import service as photoshoots
from app.providers.interface import allowed_lengths
from app.shared.types import Job, PlannedShot


def _check_text(style_text: str) -> None:
    if not style_text.strip() or len(style_text) > 4000:
        raise AppError(400, "invalid_style", "The style text must be 1 to 4000 characters.")


def _find_song(song_id: str):
    song = next((s for s in library.list_songs() if s.id == song_id), None)
    if song is None:
        raise AppError(404, "song_not_found", f"No song with id {song_id}.")
    return song


def create_job(body: JobCreate) -> Job:
    _check_text(body.style_text)
    fps, song_offset_s = 30, 0.0
    if body.style_id is not None:
        style = library.get_style(body.style_id)
        fps, song_offset_s = style.fps, style.song_offset_s
    _find_song(body.song_id)
    status = stubs.photoshoot_status(body.photoshoot_id)
    if status is None:
        raise AppError(404, "photoshoot_not_found", f"No photoshoot with id {body.photoshoot_id}.")
    if status == "awaiting_upload":
        raise AppError(409, "photoshoot_not_ready", "The photoshoot is still uploading.")
    job_id = store.insert_job(
        body.photoshoot_id,
        body.style_id,
        body.style_text,
        body.song_id,
        song_offset_s,
        fps,
        body.purpose,
    )
    job = reading.load_job(job_id)
    planning.start(job_id)
    return job


def _draft(job_id: str) -> Job:
    job = reading.load_job(job_id)
    if job.status != "draft":
        raise AppError(409, "not_draft", "The plan can only change while the job is a draft.")
    return job


def replan_job(job_id: str, body: JobReplan) -> Job:
    _draft(job_id)
    if body.style_text is not None:
        _check_text(body.style_text)
    if body.song_id is not None:
        _find_song(body.song_id)
    planning.supersede(job_id)
    store.set_planning(job_id, body.style_text, body.song_id)
    job = reading.load_job(job_id)
    planning.start(job_id)
    return job


def update_job_shots(job_id: str, shots: list[PlannedShot]) -> Job:
    job = _draft(job_id)
    if job.plan_status == "planning":
        raise AppError(409, "plan_not_ready", "The plan is still being written.")
    inputs = store.planning_inputs(job_id)
    song = _find_song(inputs["song_id"])
    photo_ids = {photo.id for photo in photoshoots.list_photos(inputs["photoshoot_id"])}
    ordered = plan_rules.renumber(shots)
    problems = plan_rules.validate_plan(
        ordered, photo_ids, song.duration_s - inputs["song_offset_s"], allowed_lengths
    )
    if problems:
        raise AppError(400, "invalid_plan", " ".join(problems))
    store.replace_plan(job_id, ordered, job.plan_notes)
    return reading.load_job(job_id)


def on_app_start() -> None:
    """Plan again any job left in planning."""
    planning.restart_interrupted()
