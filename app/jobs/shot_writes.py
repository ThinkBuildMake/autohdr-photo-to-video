"""Worker writes to shots and attempts (ARCHITECTURE: Jobs, Interface for other modules).

Every function is one short transaction whose first statement is a write that takes SQLite's
write lock, so concurrent worker threads and stopJob/finishJob are serialised. Each write is
refused with JobNotRunning once the job is no longer running.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.db.base import session_scope
from app.jobs.errors import AttemptLimitReached, JobNotRunning
from app.jobs.models import Attempt, Job, JobShot
from app.providers.errors import ProviderError
from app.shared.enums import FailureReason
from app.shared.types import ClipCheck

MAX_ATTEMPTS = 4
IN_FLIGHT = ("editing", "generating", "checking")
# target state -> states it may be set from (the same state is a detail update)
NEXT = {
    "editing": {"pending", "editing"},
    "generating": {"editing", "generating", "checking"},
    "checking": {"generating", "checking"},
}
_FAILURE_SENTENCES = {
    "refused": "The video service refused this photo.",
    "out_of_time": "Ran out of time.",
    "no_photo": "No photo of this room.",
    "job_stopped": "The job stopped before this shot finished.",
    "internal_error": "Something went wrong on our side while making this shot.",
}


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _lock_shot(session, job_shot_id: str):
    """No-op write on the shot of a running job; returns (status, round)."""
    running = select(Job.id).where(Job.status == "running")
    found = session.execute(
        update(JobShot)
        .where(JobShot.id == job_shot_id, JobShot.job_id.in_(running))
        .values(id=JobShot.id)
        .returning(JobShot.status, JobShot.round)
    ).first()
    if found is not None:
        return found
    if session.get(JobShot, job_shot_id) is None:
        raise LookupError(f"No shot with id {job_shot_id}")
    raise JobNotRunning(job_shot_id)


def _update_shot(session, job_shot_id: str, **values) -> None:
    session.execute(update(JobShot).where(JobShot.id == job_shot_id).values(**values))


def set_shot_state(job_shot_id: str, status: str, detail: str) -> None:
    with session_scope() as session:
        current, _ = _lock_shot(session, job_shot_id)
        if status not in NEXT or current not in NEXT[status]:
            raise ValueError(f"A shot cannot move from {current} to {status}")
        _update_shot(
            session, job_shot_id, status=status, status_detail=detail, updated_at=iso(now_utc())
        )


def set_shot_photo(
    job_shot_id: str,
    cropped_key: str | None,
    edited_key: str | None,
    edit_status: str,
    edit_note: str | None,
) -> None:
    with session_scope() as session:
        current, _ = _lock_shot(session, job_shot_id)
        if current != "editing":
            raise ValueError(f"A photo is recorded while editing, not {current}")
        if edit_status not in ("edited", "crop_only"):
            raise ValueError(f"Unknown edit status {edit_status}")
        _update_shot(
            session,
            job_shot_id,
            cropped_key=cropped_key,
            edited_key=edited_key,
            edit_status=edit_status,
            edit_note=edit_note,
            updated_at=iso(now_utc()),
        )


def start_attempt(job_shot_id: str, prompt: str, model: str, requested_s: float) -> str:
    with session_scope() as session:
        current, round_ = _lock_shot(session, job_shot_id)
        if current not in IN_FLIGHT:
            raise ValueError(f"An attempt cannot start while the shot is {current}")
        used = session.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.job_shot_id == job_shot_id, Attempt.round == round_)
        )
        if used >= MAX_ATTEMPTS:
            raise AttemptLimitReached(job_shot_id)
        attempt_id = str(uuid.uuid4())
        session.add(
            Attempt(
                id=attempt_id,
                job_shot_id=job_shot_id,
                round=round_,
                attempt_no=used + 1,
                prompt=prompt,
                model=model,
                requested_s=requested_s,
                status="running",
                started_at=iso(now_utc()),
            )
        )
        return attempt_id


def _attempt_detail(attempt_no: int, status: str, check, error) -> str:
    prefix = f"Attempt {attempt_no} of {MAX_ATTEMPTS}: "
    if status == "passed":
        return prefix + "passed the check"
    if status == "flagged":
        return prefix + f"flagged, {check.notes if check else 'no notes'}"
    if error is not None and error.kind in ("rate_limited", "timeout"):
        return prefix + "provider busy, trying again"
    kind = error.kind.value if error is not None else "unknown"
    return prefix + f"provider error ({kind})"


def finish_attempt(
    attempt_id: str,
    status: str,
    clip_key: str | None = None,
    check: ClipCheck | None = None,
    error: ProviderError | None = None,
    cost_usd: float = 0.0,
) -> None:
    if status not in ("passed", "flagged", "error"):
        raise ValueError(f"Unknown attempt status {status}")
    with session_scope() as session:
        shot_id = session.scalar(select(Attempt.job_shot_id).where(Attempt.id == attempt_id))
        if shot_id is None:
            raise LookupError(f"No attempt with id {attempt_id}")
        _lock_shot(session, shot_id)
        attempt = session.get(Attempt, attempt_id)
        if attempt.status != "running":
            raise ValueError(f"Attempt is already {attempt.status}")
        finished_at = iso(now_utc())
        session.execute(
            update(Attempt)
            .where(Attempt.id == attempt_id)
            .values(
                status=status,
                clip_key=clip_key,
                check_ai_score=check.ai_score if check else None,
                check_match_score=check.match_score if check else None,
                check_notes=check.notes if check else None,
                error=f"{error.kind.value}: {error.message}" if error else None,
                cost_usd=cost_usd,
                finished_at=finished_at,
            )
        )
        _update_shot(
            session,
            shot_id,
            status_detail=_attempt_detail(attempt.attempt_no, status, check, error),
            updated_at=finished_at,
        )


def _failure_detail(session, job_shot_id: str, round_: int, reason: str) -> str:
    column = {"flagged_every_attempt": Attempt.check_notes, "provider_error": Attempt.error}.get(
        reason
    )
    if column is None:
        return _FAILURE_SENTENCES[reason]
    last = session.scalar(
        select(column)
        .where(Attempt.job_shot_id == job_shot_id, Attempt.round == round_, column.is_not(None))
        .order_by(Attempt.attempt_no.desc())
        .limit(1)
    )
    return last or "No attempt succeeded."


def set_shot_result(
    job_shot_id: str,
    result: str,
    failure_reason: str | None = None,
    final_attempt_id: str | None = None,
) -> None:
    if result not in ("passed", "failed"):
        raise ValueError(f"Unknown shot result {result}")
    if result == "failed" and failure_reason not in {r.value for r in FailureReason}:
        raise ValueError(f"Unknown failure reason {failure_reason}")
    with session_scope() as session:
        current, round_ = _lock_shot(session, job_shot_id)
        now = iso(now_utc())
        if result == "passed":
            if current != "checking":
                raise ValueError(f"A shot passes from checking, not {current}")
            final = session.get(Attempt, final_attempt_id) if final_attempt_id else None
            if (
                final is None
                or final.job_shot_id != job_shot_id
                or final.round != round_
                or final.status != "passed"
            ):
                raise ValueError("A shot passes with a passed attempt of its current round")
            _update_shot(
                session,
                job_shot_id,
                status="passed",
                final_attempt_id=final.id,
                model_used=final.model,
                failure_reason=None,
                status_detail="Passed the check.",
                updated_at=now,
            )
            return
        if current != "pending" and current not in IN_FLIGHT:
            raise ValueError(f"A {current} shot cannot fail")
        _update_shot(
            session,
            job_shot_id,
            status="failed",
            failure_reason=failure_reason,
            status_detail=_failure_detail(session, job_shot_id, round_, failure_reason),
            updated_at=now,
        )
