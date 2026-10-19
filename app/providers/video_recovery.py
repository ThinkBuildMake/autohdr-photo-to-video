"""Collect clips left running at OpenRouter when the worker restarted."""

import logging
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import get_settings
from app.providers import clip_calls, video_api
from app.providers.errors import ProviderError

log = logging.getLogger(__name__)

_PENDING = ("pending", "in_progress")
_thread: threading.Thread | None = None
_DONE: set[str] = set()  # rows whose job is known completed: never closed as a timeout


def _error_of(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, httpx.HTTPError):
        return video_api.translate(exc)
    return ProviderError("bad_response", type(exc).__name__)


def _close_error(call_id: str, error: ProviderError) -> None:
    try:
        clip_calls.finish_error(call_id, error)
    except Exception:
        log.exception("Could not close provider call %s", call_id)


def _seconds_of(path: str) -> float | None:
    try:
        from app.media import service as media

        return float(media.probe(path)["durationS"])
    except Exception:
        return None


def _collect(call_id: str, model: str, job_id: str, poll: dict[str, Any]) -> None:
    """Download a completed job into the bucket and close its row."""
    from app.files import service as files

    with video_api.new_client(video_api.DOWNLOAD_TIMEOUT_S) as client:
        path = video_api.download(client, job_id, poll)
    try:
        files.put(f"clips/recovered/{call_id}.mp4", path)
        seconds = _seconds_of(path)
        if seconds is None:
            seconds = clip_calls.recorded(call_id)[2]  # the length priced when it finished
        cost, source = video_api.clip_cost(model, seconds, poll.get("usage"))
        clip_calls.finish_ok(call_id, cost, source, job_id, seconds)
    finally:
        os.unlink(path)


def _settle(client: httpx.Client, call_id: str, model: str, job_id: str) -> bool:
    """Poll one job once and close its row if the job has ended. True when closed.

    A finished job whose download or bucket put fails stays open (False): its clip is
    paid for, so it is collected again rather than abandoned.
    """
    try:
        poll = video_api.poll_job(client, job_id)
    except Exception as exc:
        _close_error(call_id, _error_of(exc))
        return True
    status = poll.get("status")
    if status in _PENDING:
        return False
    if status != "completed":
        _close_error(call_id, video_api.job_error(poll))
        return True
    _DONE.add(call_id)
    try:
        seconds = clip_calls.recorded(call_id)[2]
        cost, source = video_api.clip_cost(model, seconds, poll.get("usage"))
        clip_calls.record_cost(call_id, cost, source)
        _collect(call_id, model, job_id, poll)
    except Exception as exc:
        if video_api.is_permanent_download_error(exc) or _window_over(call_id):
            log.warning("Giving up on finished clip %s", call_id)
            _close_error(call_id, video_api.clip_lost())
            return True
        log.exception("Could not collect finished clip %s; will try again", call_id)
        return False
    return True


def _window_over(call_id: str) -> bool:
    """True once the collect window, counted from the call's start, has run out."""
    try:
        started = datetime.fromisoformat(clip_calls.recorded(call_id)[3])
    except Exception:
        return False
    hours = get_settings().CLIP_COLLECT_WINDOW_HOURS
    return (datetime.now(UTC) - started).total_seconds() >= hours * 3600


def _poll_until_done(pending: list[tuple[str, str, str]]) -> None:
    deadline = time.monotonic() + video_api.CLIP_TIMEOUT_S
    try:
        with video_api.new_client(video_api.REQUEST_TIMEOUT_S) as client:
            while pending:
                pending = [row for row in pending if not _settle(client, row[0], row[1], row[2])]
                if pending and time.monotonic() >= deadline:
                    for call_id, _, _ in pending:
                        if call_id not in _DONE:  # finished jobs stay open for the next restart
                            _close_error(
                                call_id, ProviderError("timeout", "The clip was not ready in time.")
                            )
                    return
                if pending:
                    time.sleep(video_api.POLL_INTERVAL_S)
    except Exception:
        log.exception("Background clip recovery stopped")
        for call_id, _, _ in pending:
            if call_id not in _DONE:
                _close_error(call_id, ProviderError("failed", "Clip recovery stopped."))


def recover_calls() -> None:
    """Close every generate_clip row still running. Never raises: the worker must start."""
    global _thread
    try:
        rows = clip_calls.open_clip_calls()
    except Exception:
        log.exception("Could not list open clip calls")
        return
    pending: list[tuple[str, str, str]] = []
    try:
        with video_api.new_client(video_api.REQUEST_TIMEOUT_S) as client:
            for call_id, model, job_id in rows:
                if not job_id:
                    msg = "The worker restarted before the video service answered."
                    _close_error(call_id, ProviderError("failed", msg))
                elif not _settle(client, call_id, model, job_id):
                    pending.append((call_id, model, job_id))
    except Exception:
        log.exception("Clip recovery failed")
    if pending:
        _thread = threading.Thread(
            target=_poll_until_done, args=(pending,), name="clip-recovery", daemon=True
        )
        _thread.start()
    log.info("recover_calls open=%d still_running=%d", len(rows), len(pending))


def wait_for_background() -> None:
    """Block until the background polling thread, if any, has finished."""
    if _thread is not None:
        _thread.join()
