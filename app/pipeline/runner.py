"""Pipeline: runs the next queued job, every pending shot at once up to SHOTS_IN_FLIGHT."""

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import get_settings
from app.jobs import worker_interface
from app.pipeline import clip, prepare, prompt, run
from app.shared.types import Job, JobShot

log = logging.getLogger(__name__)


def _run_shot(job: Job, shot: JobShot, folder: Path, state: run.Run) -> None:
    if not state.has_time():
        worker_interface.set_shot_result(shot.id, "failed", "out_of_time")
        return
    folder.mkdir()
    context = worker_interface.run_context(shot.id)
    frame = prepare.first_frame(
        job.id,
        job.photoshoot_id,
        shot,
        context.round_no,
        folder,
        is_running=lambda: not state.stopped,
    )
    clip.make_clip(
        job.id,
        shot,
        context.round_no,
        frame,
        prompt.build_prompt(shot),
        prompt.clip_length(shot),
        folder,
        earlier=context.earlier,
        has_time=state.has_time,
    )


def run_next_job() -> bool:
    """Returns True when a job was run, False when there was nothing to do."""
    job = worker_interface.claim_next_job()
    if job is None:
        return False
    state = run.Run.for_job(job)
    # The container's temp dir, never the database volume (STACK §5).
    with tempfile.TemporaryDirectory(prefix=f"job-{job.id}-") as folder:
        with ThreadPoolExecutor(get_settings().SHOTS_IN_FLIGHT) as pool:
            futures = [
                pool.submit(
                    state.run_shot,
                    shot.id,
                    lambda shot=shot: _run_shot(
                        job, shot, Path(folder) / str(shot.position), state
                    ),
                )
                for shot in job.shots
            ]
            for future in futures:
                future.result()
        run.finish_run(state, Path(folder))
    return True
