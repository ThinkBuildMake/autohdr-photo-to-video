"""provider_calls write path: one row per outside call, opened before and closed after it."""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.base import session_scope
from app.providers.errors import ProviderError
from app.providers.models import ProviderCall


def now_utc() -> str:
    """ISO-8601 UTC with milliseconds and a Z, the same format as NOW_UTC."""
    moment = datetime.now(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def start_call(kind: str, model: str, ids: dict[str, Any]) -> str:
    call_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            ProviderCall(
                id=call_id,
                kind=kind,
                model=model,
                job_id=ids.get("jobId"),
                job_shot_id=ids.get("jobShotId"),
                attempt_id=ids.get("attemptId"),
                photoshoot_id=ids.get("photoshootId"),
                status="running",
                started_at=now_utc(),
            )
        )
    return call_id


def finish_ok(
    call_id: str,
    cost_usd: float,
    cost_source: str,
    provider_request_id: str | None = None,
    output_seconds: float | None = None,
) -> None:
    with session_scope() as session:
        row = session.get(ProviderCall, call_id)
        if row is None:
            return
        row.status = "ok"
        row.cost_usd = cost_usd
        row.cost_source = cost_source
        row.provider_request_id = provider_request_id
        row.output_seconds = output_seconds
        row.finished_at = now_utc()


def finish_error(call_id: str, error: ProviderError, cost: tuple[float, str] | None = None) -> None:
    """Close the row as an error. Also used to turn an answer that cannot be used into an error."""
    from app.providers.chat import scrub

    with session_scope() as session:
        row = session.get(ProviderCall, call_id)
        if row is None:
            return
        row.status = "error"
        row.error_kind = str(error.kind)
        row.error_message = scrub(error.message)[:500]
        if cost is not None:
            row.cost_usd, row.cost_source = cost
        row.finished_at = now_utc()
