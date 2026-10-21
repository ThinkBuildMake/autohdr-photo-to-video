"""One shot's clip: generate, extract frames, check, store, record -- up to 4 attempts."""

import contextlib
import logging
import math
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.files import service as files
from app.files.keys import attempt_clip_key
from app.jobs import worker_interface as jobs
from app.jobs.errors import AttemptLimitReached
from app.media import service as media
from app.media.errors import MediaError
from app.pipeline.prompt import clip_length
from app.providers import interface as providers
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind
from app.shared.types import ClipResult, JobShot

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BUSY_WAIT_S = 5.0
MAX_BUSY_WAIT_S = 30.0
STORE_TRIES = 3
_BUSY = (ProviderErrorKind.rate_limited, ProviderErrorKind.timeout)


def _wait(seconds: float) -> None:
    time.sleep(seconds)


def _busy_wait_s(retry_after_s: float | None) -> float:
    """Seconds to wait after a busy answer: the provider's own, kept inside 0-30 s."""
    if retry_after_s is None or not math.isfinite(retry_after_s) or retry_after_s < 0:
        return BUSY_WAIT_S
    return min(retry_after_s, MAX_BUSY_WAIT_S)


def _store(key: str, path: str) -> None:
    """Upload a clip that is already paid for and checked: retry, never generate it again."""
    for tries in range(1, STORE_TRIES + 1):
        try:
            files.put(key, path)
            return
        except Exception:
            if tries == STORE_TRIES:
                raise
            log.warning("storing %s failed (try %d), retrying", key, tries, exc_info=True)
            _wait(tries)


@dataclass(frozen=True)
class _Reused:
    clip: jobs.RecoveredClip
    result: ClipResult

    @property
    def model(self) -> str:
        return self.clip.model

    @property
    def requested_s(self) -> float:
        return self.clip.requested_s


def _fetch_recovered(clip: jobs.RecoveredClip | None, path: Path) -> _Reused | None:
    """Download a recovered clip so it can be checked; None means generate as usual."""
    if clip is None:
        return None
    try:
        files.get(clip.key, str(path))
    except Exception:
        log.warning("recovered clip %s could not be fetched", clip.key, exc_info=True)
        return None
    result = ClipResult(
        path=str(path),
        seconds=clip.requested_s,
        model=clip.model,
        cost_usd=0.0,  # paid for already: its provider call carries the cost
        cost_source="reported",
        provider_request_id=None,
    )
    return _Reused(clip, result)


def _record_error(attempt_id: str, error: ProviderError, **fields) -> None:
    """Write the attempt's error at once (RL-1); out_of_credit then goes up to stop the job."""
    jobs.finish_attempt(attempt_id, "error", error=error, **fields)
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
    has_time: Callable[[], bool] = lambda: True,
    recovered: jobs.RecoveredClip | None = None,
) -> str | None:
    """Run the shot's attempts; return the passed attempt's id, or None when the shot failed.

    `earlier` is the round's already-recorded attempts as (model, error kind or None), oldest
    first; a resumed round replays it so a shot that switched keeps using the fallback.
    `recovered` is a paid clip collected after a restart: its first attempt checks it instead
    of generating. `has_time` is asked before every attempt; once it says no, the shot fails
    `out_of_time`.
    An unexpected error closes the running attempt as an error, then goes up to the caller.
    """
    started: list[str] = []
    try:
        return _attempts(
            job_id,
            shot,
            round_no,
            first_frame,
            prompt,
            requested_s,
            folder,
            earlier,
            has_time,
            started,
            recovered,
        )
    except ProviderError:
        raise
    except Exception as e:
        if started:
            with contextlib.suppress(Exception):
                jobs.finish_attempt(
                    started[-1],
                    "error",
                    error=ProviderError("failed", f"The worker hit an error: {type(e).__name__}"),
                )
        raise


def _attempts(
    job_id: str,
    shot: JobShot,
    round_no: int,
    first_frame: bytes,
    prompt: str,
    requested_s: float,
    folder: Path,
    earlier: Sequence[tuple[str, str | None]],
    has_time: Callable[[], bool],
    started: list[str],
    recovered: jobs.RecoveredClip | None,
) -> str | None:
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
    last = "refused" if earlier and earlier[-1][1] == "refused" else "provider_error"
    flagged = sum(kind == "flagged" for _, kind in earlier)
    errored = any(kind != "flagged" for _, kind in earlier)
    for n in range(shot.attempts + 1, MAX_ATTEMPTS + 1):
        if not has_time():
            jobs.set_shot_result(shot.id, "failed", "out_of_time")
            return None
        requested_s = clip_length(shot, model)
        reuse, recovered = _fetch_recovered(recovered, folder / f"recovered{n}.mp4"), None
        if reuse is not None:
            model, requested_s = reuse.model, reuse.requested_s
        via = f" with the fallback video model ({model})" if model == fallback != shot.model else ""
        jobs.set_shot_state(shot.id, "generating", f"Attempt {n} of 4: making the clip{via}")
        try:
            attempt_id = jobs.start_attempt(shot.id, prompt, model, requested_s)
        except AttemptLimitReached:
            break
        started.append(attempt_id)
        ids = {"jobId": job_id, "jobShotId": shot.id, "attemptId": attempt_id}
        try:
            result = (
                reuse.result
                if reuse is not None
                else providers.generate_clip(first_frame, prompt, model, requested_s, ids)
            )
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
                jobs.set_shot_state(shot.id, "generating", "Provider busy, trying again")
                _wait(_busy_wait_s(e.retry_after_s))
            continue

        path = str(folder / f"a{n}.mp4")
        shutil.move(result.path, path)
        jobs.set_shot_state(shot.id, "checking", f"Attempt {n} of 4: checking the clip{via}")
        try:
            try:
                frames = media.extract_frames(path, get_settings().CHECK_FRAMES_PER_SECOND)
            except MediaError as e:
                raise ProviderError("bad_response", "The clip could not be read") from e
            check = providers.check_clip(path, frames, first_frame, ids)
        except ProviderError as e:
            _record_error(
                attempt_id, ProviderError(e.kind, f"check: {e.message}"), cost_usd=result.cost_usd
            )
            errored = True
            last = "refused" if e.kind == ProviderErrorKind.refused else "provider_error"
            continue

        if reuse is not None:
            key = reuse.clip.key  # already stored; the normal check above still ran
        else:
            key = attempt_clip_key(job_id, shot.position, round_no, n)
            _store(key, path)
        if check.passed:
            jobs.finish_attempt(
                attempt_id, "passed", clip_key=key, check=check, cost_usd=result.cost_usd
            )
            jobs.set_shot_result(shot.id, "passed", final_attempt_id=attempt_id)
            return attempt_id
        jobs.finish_attempt(
            attempt_id, "flagged", clip_key=key, check=check, cost_usd=result.cost_usd
        )
        flagged += 1

    if flagged and not errored:
        last = "flagged_every_attempt"
    jobs.set_shot_result(shot.id, "failed", last)
    return None
