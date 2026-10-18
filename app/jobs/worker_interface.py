"""Jobs interface for the worker (ARCHITECTURE: Jobs, Interface for other modules).

Stub: S29 builds it. claim_next_job finds nothing and recover_interrupted does nothing.
"""

from app.shared.types import ClipCheck, Job

_NOT_BUILT = "Jobs worker interface is built in S29."


def claim_next_job() -> Job | None:
    return None


def recover_interrupted() -> None:
    return None


def set_shot_state(job_shot_id: str, status: str, detail: str) -> None:
    raise NotImplementedError(_NOT_BUILT)


def set_shot_photo(
    job_shot_id: str,
    cropped_key: str,
    edited_key: str | None,
    edit_status: str,
    edit_note: str | None,
) -> None:
    raise NotImplementedError(_NOT_BUILT)


def start_attempt(job_shot_id: str, prompt: str, model: str, requested_s: float) -> str:
    raise NotImplementedError(_NOT_BUILT)


def finish_attempt(
    attempt_id: str,
    status: str,
    clip_key: str | None = None,
    check: ClipCheck | None = None,
    error=None,
    cost_usd: float = 0.0,
) -> None:
    raise NotImplementedError(_NOT_BUILT)


def set_shot_result(
    job_shot_id: str,
    result: str,
    failure_reason: str | None = None,
    final_attempt_id: str | None = None,
) -> None:
    raise NotImplementedError(_NOT_BUILT)


def finish_job(
    job_id: str, status: str, stop_reason: str | None = None, video: dict | None = None
) -> None:
    raise NotImplementedError(_NOT_BUILT)


def stop_job(job_id: str, stop_reason: str) -> None:
    raise NotImplementedError(_NOT_BUILT)
