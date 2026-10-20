"""Pipeline: runs the next queued job, every pending shot at once up to SHOTS_IN_FLIGHT."""

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import get_settings
from app.jobs import worker_interface
from app.pipeline import clip, prepare, prompt, stubs
from app.shared.types import Job, JobShot

log = logging.getLogger(__name__)


def _run_shot(job: Job, shot: JobShot, folder: Path) -> None:
    try:
        folder.mkdir()
        round_no = stubs.shot_round(shot.id)
        frame = prepare.first_frame(job.id, job.photoshoot_id, shot, round_no, folder)
        clip.make_clip(
            job.id,
            shot,
            round_no,
            frame,
            prompt.build_prompt(shot),
            prompt.clip_length(shot),
            folder,
        )
    except Exception:
        log.exception("shot %s of job %s stopped", shot.position, job.id)


def run_next_job() -> bool:
    """Returns True when a job was run, False when there was nothing to do."""
    job = worker_interface.claim_next_job()
    if job is None:
        return False
    # The container's temp dir, never the database volume (STACK §5).
    with (
        tempfile.TemporaryDirectory(prefix=f"job-{job.id}-") as folder,
        ThreadPoolExecutor(get_settings().SHOTS_IN_FLIGHT) as pool,
    ):
        for shot in job.shots:
            pool.submit(_run_shot, job, shot, Path(folder) / str(shot.position))
    return True
