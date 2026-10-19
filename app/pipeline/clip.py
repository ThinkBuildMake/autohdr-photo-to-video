"""One shot's clip: generate, extract frames, check, store, record -- up to 4 attempts."""

import logging
import math
import shutil
import time
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.files.keys import attempt_clip_key
from app.jobs.errors import AttemptLimitReached
from app.media.errors import MediaError
from app.pipeline import clip_stubs
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind
from app.shared.types import JobShot

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BUSY_WAIT_S = 5.0
MAX_BUSY_WAIT_S = 30.0
_BUSY = (ProviderErrorKind.rate_limited, ProviderErrorKind.timeout)


def _wait(seconds: float) -> None:
    time.sleep(seconds)


def _busy_wait_s(retry_after_s: float | None) -> float:
    """Seconds to wait after a busy answer: the provider's own, kept inside 0-30 s."""
    if retry_after_s is None or not math.isfinite(retry_after_s) or retry_after_s < 0:
        return BUSY_WAIT_S
    return min(retry_after_s, MAX_BUSY_WAIT_S)


def _record_error(attempt_id: str, error: ProviderError, **fields) -> None:
    """Write the attempt's error at once (RL-1); out_of_credit then goes up to stop the job."""
    clip_stubs.finish_attempt(attempt_id, "error", error=error, **fields)
    log.warning("attempt %s failed: %s", attempt_id, error.kind)
    if error.kind == ProviderErrorKind.out_of_credit:
        raise error


def make_clip(
    job_id: str,
    shot: JobShot,
    round_no: int,
    first_frame: bytes,
    prompt: str,
    requested_s: float,
    folder: Path,
    earlier: Sequence[tuple[str, str | None]] = (),
) -> str | None:
    """Run the shot's attempts; return the passed attempt's id, or None when the shot failed.

    `earlier` is the round's already-recorded attempts as (model, error kind or None), oldest
    first; a resumed round replays it so a shot that switched keeps using the fallback.
    """
    fallback = get_settings().VIDEO_MODEL_FALLBACK
    model = fallback if shot.used_fallback else shot.model
    failures = 0
    for used, kind in earlier:
        if kind == ProviderErrorKind.refused:
            model = fallback
        elif kind == ProviderErrorKind.failed and used == model:
            failures += 1
            if failures >= 2:
                model = fallback
    last = "provider_error"
    flagged = 0
    errored = False
    for n in range(shot.attempts + 1, MAX_ATTEMPTS + 1):
        via = f" with the fallback video model ({model})" if model == fallback != shot.model else ""
        clip_stubs.set_shot_state(shot.id, "generating", f"Attempt {n} of 4: making the clip{via}")
        try:
            attempt_id = clip_stubs.start_attempt(shot.id, prompt, model, requested_s)
        except AttemptLimitReached:
            break
        ids = {"jobId": job_id, "jobShotId": shot.id, "attemptId": attempt_id}
        try:
            result = clip_stubs.generate_clip(first_frame, prompt, model, requested_s, ids)
        except ProviderError as e:
            _record_error(attempt_id, e)
            errored = True
            last = "refused" if e.kind == ProviderErrorKind.refused else "provider_error"
            if e.kind == ProviderErrorKind.refused:
                if model == fallback:
                    break
                model = fallback
            elif e.kind == ProviderErrorKind.failed:
                failures += 1
                if failures >= 2:
                    model = fallback
            elif e.kind in _BUSY and n < MAX_ATTEMPTS:
                clip_stubs.set_shot_state(shot.id, "generating", "Provider busy, trying again")
                _wait(_busy_wait_s(e.retry_after_s))
            continue

        path = str(folder / f"a{n}.mp4")
        shutil.move(result.path, path)
        clip_stubs.set_shot_state(shot.id, "checking", f"Attempt {n} of 4: checking the clip{via}")
        try:
            try:
                frames = clip_stubs.extract_frames(path, get_settings().CHECK_FRAMES_PER_SECOND)
            except MediaError as e:
                raise ProviderError("bad_response", "The clip could not be read") from e
            check = clip_stubs.check_clip(path, frames, first_frame, ids)
        except ProviderError as e:
            _record_error(attempt_id, e, cost_usd=result.cost_usd)
            errored = True
            last = "refused" if e.kind == ProviderErrorKind.refused else "provider_error"
            continue

        key = attempt_clip_key(job_id, shot.position, round_no, n)
        clip_stubs.put(key, path)
        if check.passed:
            clip_stubs.finish_attempt(
                attempt_id, "passed", clip_key=key, check=check, cost_usd=result.cost_usd
            )
            clip_stubs.set_shot_result(shot.id, "passed", final_attempt_id=attempt_id)
            return attempt_id
        clip_stubs.finish_attempt(
            attempt_id, "flagged", clip_key=key, check=check, cost_usd=result.cost_usd
        )
        flagged += 1

    if flagged and not errored:
        last = "flagged_every_attempt"
    clip_stubs.set_shot_result(shot.id, "failed", last)
    return None
