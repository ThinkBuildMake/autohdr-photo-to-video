"""Stand-ins S28 borrows until S22 removes them.

Jobs (set_shot_state, start_attempt, finish_attempt, set_shot_result), Providers (generate_clip,
check_clip), Media (extract_frames) and Files (put and get, on the in-memory BUCKET; S30's
assembly reads clips back with get). Signatures match
the architecture so S22 swaps in the real calls. Named clip_stubs so it never collides with
app/pipeline/stubs.py.
"""

import tempfile
import uuid
from os import close

from app.shared.types import ClipCheck, ClipResult

BUCKET: dict[str, bytes] = {}


def set_shot_state(job_shot_id: str, status: str, detail: str) -> None:
    return None


def start_attempt(job_shot_id: str, prompt: str, model: str, requested_s: float) -> str:
    return str(uuid.uuid4())


def finish_attempt(
    attempt_id: str,
    status: str,
    clip_key: str | None = None,
    check: ClipCheck | None = None,
    error: Exception | None = None,
    cost_usd: float = 0.0,
) -> None:
    return None


def set_shot_result(
    job_shot_id: str,
    result: str,
    failure_reason: str | None = None,
    final_attempt_id: str | None = None,
) -> None:
    return None


def generate_clip(
    first_frame_jpeg: bytes, prompt: str, model: str, length_s: float, ids: dict[str, str]
) -> ClipResult:
    fd, path = tempfile.mkstemp(suffix=".mp4")
    close(fd)
    return ClipResult(
        path=path,
        seconds=length_s,
        model=model,
        cost_usd=0.0,
        cost_source="reported",
        provider_request_id=None,
    )


def check_clip(
    clip_path: str, frames: list[bytes], source_jpeg: bytes, ids: dict[str, str]
) -> ClipCheck:
    return ClipCheck(
        ai_score=0.0,
        match_score=1.0,
        people_count=0,
        added_objects=[],
        removed_objects=[],
        changed_objects=[],
        passed=True,
        notes="",
    )


def extract_frames(clip_path: str, per_second: float) -> list[bytes]:
    return []


def put(key: str, path: str) -> None:
    with open(path, "rb") as handle:
        BUCKET[key] = handle.read()


def get(key: str, path: str) -> None:
    with open(path, "wb") as handle:
        handle.write(BUCKET[key])
