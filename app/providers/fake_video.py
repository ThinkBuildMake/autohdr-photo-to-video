"""Fake generate_clip: a real, short test clip made by ffmpeg, with scripted failures.

FakeProviders is rebuilt on every interface call, so state lives here at module level.
"""

import os
import subprocess
import tempfile
import threading
import uuid
from typing import Any

from app.providers import calls as clip_calls
from app.providers.errors import ProviderError
from app.shared.types import ClipResult

_lock = threading.Lock()
_call_count = 0
_scripts: dict[int, str] = {}


def fail_on(call_no: int, error_kind: str) -> None:
    """Make the call_no-th generate_clip call (1-based, since reset) fail with error_kind."""
    with _lock:
        _scripts[call_no] = error_kind


def reset() -> None:
    global _call_count
    with _lock:
        _call_count = 0
        _scripts.clear()


def _next_script() -> str | None:
    global _call_count
    with _lock:
        _call_count += 1
        return _scripts.get(_call_count)


def _fail(call_id: str, kind: str, message: str) -> ProviderError:
    error = ProviderError(kind, message)
    clip_calls.finish_error(call_id, error)
    return error


def generate_clip(
    first_frame_jpeg: bytes,
    prompt: str,
    model: str,
    length_s: float,
    ids: dict[str, Any],
) -> ClipResult:
    call_id = clip_calls.start_call(clip_calls.KIND, model, ids)
    scripted = _next_script()
    if scripted is not None:
        raise _fail(call_id, scripted, "fake generate_clip error")
    handle, path = tempfile.mkstemp(suffix=".mp4")
    os.close(handle)
    command = [
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", "testsrc2=size=1920x1080:rate=24", "-t", str(length_s),
        "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path,
    ]  # fmt: skip
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError) as exc:
        raise _fail(
            call_id, "failed", f"fake clip could not be made: {type(exc).__name__}"
        ) from exc
    request_id = f"fake-{uuid.uuid4()}"
    clip_calls.finish_ok(call_id, 0.0, "reported", request_id, length_s)
    return ClipResult(
        path=path,
        seconds=length_s,
        model=model,
        cost_usd=0.0,
        cost_source="reported",
        provider_request_id=request_id,
    )


def allowed_lengths(model: str) -> list[float]:
    if model == "bytedance/seedance-2.0":
        return [float(n) for n in range(4, 16)]
    return [4.0, 6.0, 8.0]
