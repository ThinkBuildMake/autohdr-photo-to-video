"""One shot's first frame: crop to 16:9, then the photo-edit chain with its check (step 1)."""

import logging
from collections.abc import Callable
from pathlib import Path

from app.config import get_settings
from app.files import service as files
from app.files.keys import frame_key
from app.jobs import worker_interface as jobs
from app.jobs.errors import JobNotRunning
from app.media import service as media
from app.photoshoots import service as photoshoots
from app.providers import interface as providers
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind
from app.shared.types import JobShot

log = logging.getLogger(__name__)


def _store(job_id: str, shot: JobShot, round_no: int, folder: Path, name: str, jpeg: bytes) -> str:
    key = frame_key(job_id, shot.position, round_no, name)
    path = folder / f"{name}.jpg"
    path.write_bytes(jpeg)
    files.put(key, str(path))
    return key


def _edit(
    crop: bytes, prompts: list[str], ids: dict[str, str], ensure_running: Callable[[], None]
) -> tuple[bytes | None, str]:
    """The checked edit, or None and why: the chain runs twice per model at most, so a changed
    room is retried once; a failing image model moves the chain to the fallback model."""
    settings = get_settings()
    note = "The image model could not edit this photo"
    changed_retries = 0
    for model in dict.fromkeys(
        filter(None, (settings.ENHANCE_MODEL, settings.ENHANCE_MODEL_FALLBACK))
    ):
        for _ in range(2):
            edited = crop
            try:
                for prompt in prompts:
                    ensure_running()
                    edited = providers.edit_photo(edited, prompt, ids, model)
            except ProviderError as e:
                if e.kind == ProviderErrorKind.out_of_credit:
                    raise
                if changed_retries:
                    return None, note
                log.warning("edit on %s failed: %s", model, e.kind)
                break
            try:
                ensure_running()
                check = providers.check_edit(crop, edited, ids)
            except ProviderError as e:
                if e.kind == ProviderErrorKind.out_of_credit:
                    raise
                return None, "The edit could not be checked"
            if not check.architecture_changed:
                return edited, ""
            note = f"The edit changed the room: {check.notes}"
            changed_retries += 1
            if changed_retries >= 2:
                return None, note
        else:
            return None, note
    return None, note


def first_frame(
    job_id: str,
    photoshoot_id: str,
    shot: JobShot,
    round_no: int,
    folder: Path,
    *,
    is_running: Callable[[], bool] = lambda: True,
) -> bytes:
    def ensure_running() -> None:
        if not is_running():
            raise JobNotRunning()

    ensure_running()
    jobs.set_shot_state(shot.id, "editing", "Preparing the photo")
    crop = media.crop16x9(photoshoots.photo_bytes(photoshoot_id, shot.photo_id))
    cropped_key = _store(job_id, shot, round_no, folder, "cropped", crop)
    edited, note = None, None
    if shot.photo_edit_prompts:
        ids = {"jobId": job_id, "jobShotId": shot.id}
        edited, note = _edit(crop, shot.photo_edit_prompts, ids, ensure_running)
    ensure_running()
    if edited is None:
        jobs.set_shot_photo(shot.id, cropped_key, None, "crop_only", note)
        return crop
    edited_key = _store(job_id, shot, round_no, folder, "edited", edited)
    jobs.set_shot_photo(shot.id, cropped_key, edited_key, "edited", None)
    return edited
