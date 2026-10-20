"""planJob: the background job that writes a draft's shot plan from its style text."""

import contextlib
import threading
from functools import partial

from pydantic import ValidationError

from app.config import get_settings
from app.jobs import plan_rules, store
from app.jobs.errors import JobNotFound
from app.library import service as library
from app.photoshoots import service as photoshoots
from app.providers.errors import ProviderError
from app.providers.interface import allowed_lengths, plan_shots
from app.shared.types import PlannedShot

_lock = threading.Lock()
_generations: dict[str, int] = {}
_threads: list[threading.Thread] = []


def _bump(job_id: str) -> int:
    with _lock:
        _generations[job_id] = _generations.get(job_id, 0) + 1
        return _generations[job_id]


def supersede(job_id: str) -> None:
    """Make any plan still running for this job stale, so it cannot write."""
    _bump(job_id)


def start(job_id: str) -> None:
    generation = _bump(job_id)
    thread = threading.Thread(
        target=plan_job, args=(job_id, generation), name=f"plan-{job_id}", daemon=True
    )
    with _lock:
        _threads[:] = [t for t in _threads if t.is_alive()]
        _threads.append(thread)
    thread.start()


def wait_idle(timeout: float = 10) -> None:
    with _lock:
        running = list(_threads)
    for thread in running:
        thread.join(timeout)


def restart_interrupted() -> None:
    for job_id in store.jobs_left_planning():
        start(job_id)


def plan_job(job_id: str, generation: int | None = None) -> None:
    try:
        _plan(job_id, generation)
    except Exception as error:
        reason = str(error) or repr(error)
        with contextlib.suppress(JobNotFound):
            _write(job_id, generation, lambda: store.set_plan_failed(job_id, reason))


def _current(job_id: str, generation: int | None) -> bool:
    if generation is not None and _generations.get(job_id) != generation:
        return False
    inputs = store.planning_inputs(job_id)
    return inputs["status"] == "draft" and inputs["plan_status"] == "planning"


def _write(job_id: str, generation: int | None, action) -> None:
    """Run a store write only if this run is still the current one for a draft being planned."""
    with _lock:
        if _current(job_id, generation):
            action()


def _off_menu(shots: list[PlannedShot], model: str, lengths: list[float]) -> list[str]:
    """The planner was offered one menu of lengths for the job's video model."""
    allowed = set(lengths)
    return [
        f"Shot {n}: {shot.length_s:g} s is not an allowed length."
        for n, shot in enumerate(shots, start=1)
        if shot.model == model and shot.length_s not in allowed
    ]


def _plan(job_id: str, generation: int | None) -> None:
    inputs = store.planning_inputs(job_id)
    song = next(s for s in library.list_songs() if s.id == inputs["song_id"])
    budget = song.duration_s - inputs["song_offset_s"]
    photos = photoshoots.planner_photos(inputs["photoshoot_id"])
    photo_ids = {p["photoId"] for p in photos}
    lengths = allowed_lengths(get_settings().VIDEO_MODEL)
    ids = {"jobId": job_id, "photoshootId": inputs["photoshoot_id"]}

    text = inputs["style_text"]
    problems: list[str] = []
    for _ in range(2):
        try:
            answer = plan_shots(text, budget, photos, plan_rules.MOVEMENTS, lengths, ids)
            shots = plan_rules.renumber([PlannedShot.model_validate(s) for s in answer["shots"]])
            problems = plan_rules.validate_plan(shots, photo_ids, budget, allowed_lengths)
            problems.extend(_off_menu(shots, get_settings().VIDEO_MODEL, lengths))
        except (ProviderError, ValidationError) as error:
            problems = [str(error)]
        if not problems:
            _write(job_id, generation, partial(store.replace_plan, job_id, shots, answer["notes"]))
            return
        text = inputs["style_text"] + "\n\nYour last plan was refused: " + " ".join(problems)
    reason = "The planner's plan was invalid twice: " + " ".join(problems)
    _write(job_id, generation, partial(store.set_plan_failed, job_id, reason))
