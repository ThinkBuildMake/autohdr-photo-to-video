"""generate_clip through OpenRouter's Videos API: submit, poll, download. Never retries."""

import base64
import logging
import os
import time
from typing import Any

import httpx

from app.providers import clip_calls, video_api
from app.providers.errors import ProviderError
from app.shared.types import ClipResult

log = logging.getLogger(__name__)

_TERMINAL_BAD = ("failed", "cancelled", "expired")


def _body(first_frame_jpeg: bytes, prompt: str, model: str, length_s: float) -> dict[str, Any]:
    data_url = "data:image/jpeg;base64," + base64.b64encode(first_frame_jpeg).decode()
    return {
        "model": model,
        "prompt": prompt,
        "duration": int(length_s) if float(length_s).is_integer() else length_s,
        "resolution": video_api.resolution_for(model),
        "aspect_ratio": "16:9",
        "generate_audio": False,
        "frame_images": [
            {
                "type": "image_url",
                "image_url": {"url": data_url},
                "frame_type": "first_frame",
            }
        ],
    }


def _as_error(exc: Exception) -> ProviderError:
    if isinstance(exc, httpx.HTTPError):
        return video_api.translate(exc)
    return ProviderError("bad_response", type(exc).__name__)


def _run(call_id: str, first_frame_jpeg: bytes, prompt: str, model: str, length_s: float):
    base = video_api.base_url()
    with video_api.new_client(video_api.REQUEST_TIMEOUT_S) as client:
        response = client.post(
            f"{base}/videos",
            headers=video_api.auth_headers(),
            json=_body(first_frame_jpeg, prompt, model, length_s),
        )
        if response.status_code >= 400:
            raise video_api.http_error(response)
        job_id = response.json().get("id")
        if not job_id:
            raise ProviderError("bad_response", "The video service gave no job id.")
        clip_calls.set_request_id(call_id, job_id)
        deadline = time.monotonic() + video_api.CLIP_TIMEOUT_S
        while True:
            poll = video_api.poll_job(client, job_id)
            status = poll.get("status")
            if status == "completed":
                break
            if status in _TERMINAL_BAD:
                raise video_api.job_error(poll)
            if time.monotonic() >= deadline:
                raise ProviderError("timeout", "The clip was not ready in time.")
            time.sleep(video_api.POLL_INTERVAL_S)
    cost, source = video_api.clip_cost(model, length_s, poll.get("usage"))
    clip_calls.record_cost(call_id, cost, source, length_s)
    try:
        with video_api.new_client(video_api.DOWNLOAD_TIMEOUT_S) as client:
            path = video_api.download(client, job_id, poll)
    except Exception as exc:
        error = exc if isinstance(exc, ProviderError) else _as_error(exc)
        if video_api.is_permanent_download_error(exc):
            # The clip is gone for good: close the row now, keeping the recorded cost.
            raise video_api.clip_lost() from exc
        # Paid for and maybe only briefly unavailable: keep the row running for recover_calls.
        error.leave_open = True
        raise error from exc
    try:
        clip_calls.finish_ok(call_id, cost, source, job_id, length_s)
    except BaseException:
        os.unlink(path)
        raise
    return ClipResult(
        path=path,
        seconds=length_s,
        model=model,
        cost_usd=cost,
        cost_source=source,
        provider_request_id=job_id,
    )


def generate_clip(
    first_frame_jpeg: bytes,
    prompt: str,
    model: str,
    length_s: float,
    ids: dict[str, Any],
) -> ClipResult:
    call_id = clip_calls.start(clip_calls.KIND, model, ids)
    try:
        try:
            result = _run(call_id, first_frame_jpeg, prompt, model, length_s)
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise video_api.translate(exc) from exc
        except Exception as exc:
            raise ProviderError("bad_response", type(exc).__name__) from exc
    except ProviderError as error:
        if getattr(error, "leave_open", False):
            log.warning(
                "generate_clip model=%s finished but not downloaded; left for recovery", model
            )
            raise
        clip_calls.finish_error(call_id, error)
        log.info("generate_clip model=%s status=error error_kind=%s", model, error.kind)
        raise
    log.info("generate_clip model=%s status=ok error_kind=-", model)
    return result
