"""OpenRouter Videos API pieces: errors, the cached model list, polling, download and cost."""

import logging
import os
import tempfile
import threading
from typing import Any
from urllib.parse import urlparse

import httpx

from app.access.scrubbing import scrub
from app.config import get_settings
from app.providers.errors import ProviderError

log = logging.getLogger(__name__)

# Test hook: tests install an httpx.MockTransport here.
TRANSPORT: httpx.BaseTransport | None = None

POLL_INTERVAL_S = 10
CLIP_TIMEOUT_S = 1200
REQUEST_TIMEOUT_S = 60
DOWNLOAD_TIMEOUT_S = 300

_models_lock = threading.Lock()
_models: dict[str, dict[str, Any]] | None = None


def base_url() -> str:
    return get_settings().OPENROUTER_BASE_URL.rstrip("/")


def new_client(timeout_s: float) -> httpx.Client:
    return httpx.Client(transport=TRANSPORT, timeout=timeout_s, follow_redirects=True)


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().OPENROUTER_API_KEY}"}


def _message(text: str) -> str:
    return scrub(text)[:500]


def _error_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, dict) else {}


def _has_reasons(error: dict[str, Any]) -> bool:
    metadata = error.get("metadata")
    return isinstance(metadata, dict) and bool(metadata.get("reasons"))


def http_error(response: httpx.Response) -> ProviderError:
    """Map an error answer to a ProviderError. The caller never retries."""
    status = response.status_code
    error = _error_body(response)
    message = _message(f"HTTP {status}: {error.get('message', '')}")
    if status == 429:
        retry_after = None
        try:
            retry_after = float(response.headers.get("Retry-After", ""))
        except ValueError:
            pass
        return ProviderError("rate_limited", message, retry_after)
    if status == 402:
        return ProviderError("out_of_credit", message)
    if status == 403 or _has_reasons(error):
        return ProviderError("refused", message)
    if status == 408:
        return ProviderError("timeout", message)
    return ProviderError("failed", message)


PERMANENT_DOWNLOAD_STATUSES = (403, 404, 410)
CLIP_LOST_MESSAGE = "The clip finished but could not be downloaded."


def is_permanent_download_error(exc: BaseException) -> bool:
    """True when the content URL answered a 4xx that retrying will not change."""
    return getattr(exc, "http_status", None) in PERMANENT_DOWNLOAD_STATUSES


def clip_lost() -> ProviderError:
    return ProviderError("failed", CLIP_LOST_MESSAGE)


def job_error(poll_body: dict[str, Any]) -> ProviderError:
    """Map a poll answer whose job failed, was cancelled or expired."""
    error = poll_body.get("error")
    error = error if isinstance(error, dict) else {}
    status = poll_body.get("status", "failed")
    message = _message(f"Video job {status}: {error.get('message') or ''}")
    if str(error.get("code")) == "403" or _has_reasons(error):
        return ProviderError("refused", message)
    return ProviderError("failed", message)


def translate(exc: Exception) -> ProviderError:
    """Transport exceptions become a ProviderError naming only the exception type."""
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError("timeout", type(exc).__name__)
    return ProviderError("failed", type(exc).__name__)


def reset_cache() -> None:
    global _models
    with _models_lock:
        _models = None


def _load_models() -> dict[str, dict[str, Any]]:
    global _models
    with _models_lock:
        if _models is not None:
            return _models
        try:
            with new_client(REQUEST_TIMEOUT_S) as client:
                response = client.get(f"{base_url()}/videos/models", headers=auth_headers())
        except httpx.HTTPError as exc:
            raise translate(exc) from exc
        if response.status_code >= 400:
            raise http_error(response)
        try:
            listed = response.json()["data"]
            parsed: dict[str, dict[str, Any]] = {}
            for entry in listed:
                skus = entry.get("pricing_skus") or {}
                price = skus.get("duration_seconds_without_audio")
                parsed[entry["id"]] = {
                    "lengths": [float(d) for d in entry.get("supported_durations") or []],
                    "price": float(price) if price not in (None, "") else None,
                }
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderError("bad_response", "The video model list could not be read.") from exc
        _models = parsed
        return parsed


def _model_entry(model: str) -> dict[str, Any]:
    entry = _load_models().get(model)
    if entry is None:
        raise ProviderError(
            "bad_response", _message(f"Model {model} is not in the video model list.")
        )
    return entry


def allowed_lengths(model: str) -> list[float]:
    return list(_model_entry(model)["lengths"])


def price_per_second(model: str) -> float | None:
    return _model_entry(model)["price"]


def resolution_for(model: str) -> str:
    for item in get_settings().VIDEO_RESOLUTIONS.split(","):
        name, _, value = item.partition("=")
        if name.strip() == model and value.strip():
            return value.strip()
    return "1080p"


def poll_job(client: httpx.Client, job_id: str) -> dict[str, Any]:
    response = client.get(f"{base_url()}/videos/{job_id}", headers=auth_headers())
    if response.status_code >= 400:
        raise http_error(response)
    body = response.json()
    if not isinstance(body, dict):
        raise ProviderError("bad_response", "The video service answered with an unexpected shape.")
    return body


def _content_url(job_id: str, poll_body: dict[str, Any]) -> str:
    urls = poll_body.get("unsigned_urls")
    if isinstance(urls, list) and urls and isinstance(urls[0], str):
        if urlparse(urls[0]).hostname == urlparse(base_url()).hostname:
            return urls[0]
    return f"{base_url()}/videos/{job_id}/content?index=0"


def download(client: httpx.Client, job_id: str, poll_body: dict[str, Any]) -> str:
    """Stream the finished clip into a new temp .mp4 and return its path."""
    handle, path = tempfile.mkstemp(suffix=".mp4")
    try:
        with (
            os.fdopen(handle, "wb") as out,
            client.stream("GET", _content_url(job_id, poll_body), headers=auth_headers()) as r,
        ):
            if r.status_code >= 400:
                r.read()
                error = http_error(r)
                error.http_status = r.status_code
                raise error
            for chunk in r.iter_bytes():
                out.write(chunk)
    except BaseException:
        os.unlink(path)
        raise
    return path


def configured_price(model: str) -> float | None:
    for item in get_settings().VIDEO_LIST_PRICES.split(","):
        name, _, value = item.partition("=")
        if name.strip() == model:
            try:
                return float(value)
            except ValueError:
                return None
    return None


def clip_cost(model: str, seconds: float | None, usage: dict[str, Any] | None) -> tuple[float, str]:
    usage = usage or {}
    byok = usage.get("is_byok") is True or model in {
        m.strip() for m in get_settings().BYOK_MODELS.split(",") if m.strip()
    }
    if not byok:
        return float(usage.get("cost") or 0.0), "reported"
    try:
        price = price_per_second(model)
    except ProviderError as error:
        log.warning("Price lookup for %s failed (%s); trying configured", model, error.kind)
        price = None
    if price is None:
        price = configured_price(model)
        if price is not None:
            log.warning("Using the configured list price %s/s for %s", price, model)
    if price is None or seconds is None:
        log.warning("No per-second list price for %s; recording 0.0", model)
        return 0.0, "list_price"
    return seconds * price, "list_price"
