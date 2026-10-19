"""provider_calls rows for generate_clip calls. Each function is its own short transaction."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.access.scrubbing import scrub
from app.db.base import session_scope
from app.providers.errors import ProviderError
from app.providers.models import ProviderCall

KIND = "generate_clip"


def now_utc() -> str:
    """ISO-8601 UTC with milliseconds and a Z, the same format as NOW_UTC."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def start(kind: str, model: str, ids: dict[str, Any]) -> str:
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


def set_request_id(call_id: str, provider_request_id: str) -> None:
    with session_scope() as session:
        session.get(ProviderCall, call_id).provider_request_id = provider_request_id


def finish_ok(
    call_id: str,
    cost_usd: float,
    cost_source: str,
    provider_request_id: str | None,
    output_seconds: float,
) -> None:
    with session_scope() as session:
        call = session.get(ProviderCall, call_id)
        call.status = "ok"
        if call.cost_usd is None or cost_usd >= call.cost_usd:
            call.cost_usd = cost_usd
            call.cost_source = cost_source
        call.provider_request_id = provider_request_id
        call.output_seconds = output_seconds
        call.finished_at = now_utc()


def record_cost(
    call_id: str, cost_usd: float, cost_source: str, output_seconds: float | None = None
) -> None:
    """Note the cost of a finished job on a row that stays running until its clip is collected.

    Never lowers a cost already on the row, and keeps the seconds it was priced for.
    """
    with session_scope() as session:
        call = session.get(ProviderCall, call_id)
        if call.cost_usd is None or cost_usd >= call.cost_usd:
            call.cost_usd = cost_usd
            call.cost_source = cost_source
        if output_seconds is not None:
            call.output_seconds = output_seconds


def recorded(call_id: str) -> tuple[float | None, str | None, float | None, str]:
    """(cost_usd, cost_source, output_seconds, started_at) now on the row."""
    with session_scope() as session:
        call = session.get(ProviderCall, call_id)
        return call.cost_usd, call.cost_source, call.output_seconds, call.started_at


def finish_error(call_id: str, error: ProviderError) -> None:
    with session_scope() as session:
        call = session.get(ProviderCall, call_id)
        call.status = "error"
        call.error_kind = str(error.kind)
        call.error_message = scrub(error.message)[:500]
        call.finished_at = now_utc()


def open_clip_calls() -> list[tuple[str, str, str | None]]:
    """(id, model, provider_request_id) of generate_clip calls still running."""
    with session_scope() as session:
        rows = session.execute(
            select(ProviderCall.id, ProviderCall.model, ProviderCall.provider_request_id).where(
                ProviderCall.kind == KIND, ProviderCall.status == "running"
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]
