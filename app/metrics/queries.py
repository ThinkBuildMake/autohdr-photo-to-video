"""Read-only queries behind the metrics report. Each returns a number, or None with no rows."""

from statistics import median

from sqlalchemy import text
from sqlalchemy.orm import Session

_SECONDS = 86400.0


def _only(column: str, job_ids: list[str] | None) -> tuple[str, dict]:
    """An ` AND column IN (...)` clause and its parameters; empty when every job counts."""
    if job_ids is None:
        return "", {}
    names = {f"jid{i}": job_id for i, job_id in enumerate(job_ids)}
    marks = ", ".join(f":{n}" for n in names) or "NULL"
    return f" AND {column} IN ({marks})", names


def _waits(session: Session, job_ids: list[str] | None) -> list[float]:
    only, params = _only("id", job_ids)
    rows = session.execute(
        text(
            "SELECT (julianday(first_finished_at) - julianday(first_submitted_at)) * :day "
            "FROM jobs WHERE first_submitted_at IS NOT NULL AND first_finished_at IS NOT NULL"
            + only
        ),
        {"day": _SECONDS, **params},
    )
    return [row[0] for row in rows]


def slowest_wait_s(session: Session, job_ids: list[str] | None = None) -> float | None:
    waits = _waits(session, job_ids)
    return max(waits) if waits else None


def typical_wait_s(session: Session, job_ids: list[str] | None = None) -> float | None:
    waits = _waits(session, job_ids)
    return median(waits) if waits else None


def provider_error_delays(session: Session, job_ids: list[str] | None = None) -> list[dict]:
    """Persisted message availability; browser polling is measured separately.

    An attempt's error shows when the attempt is written. A call with no attempt shows only
    when it stopped the job (out of credit, in this run); other such calls are unmeasured.
    """
    only, params = _only("c.job_id", job_ids)
    return [
        dict(row)
        for row in session.execute(
            text(
                "SELECT c.id AS call_id, c.job_id, c.job_shot_id, c.attempt_id, c.error_kind, "
                "CASE WHEN c.finished_at IS NOT NULL THEN "
                "(julianday(COALESCE(a.finished_at, "
                "CASE WHEN j.status = 'stopped' AND j.stop_reason = 'out_of_credit' "
                "AND c.error_kind = 'out_of_credit' AND c.finished_at >= j.started_at "
                "AND j.finished_at >= c.finished_at THEN j.finished_at END)) "
                "- julianday(c.finished_at)) * :day END AS delay_s "
                "FROM provider_calls c LEFT JOIN attempts a ON a.id = c.attempt_id "
                "LEFT JOIN jobs j ON j.id = c.job_id "
                "WHERE c.status = 'error'" + only + " ORDER BY c.started_at, c.id"
            ),
            {"day": _SECONDS, **params},
        ).mappings()
    ]


def provider_error_to_user_s(session: Session, job_ids: list[str] | None = None) -> float | None:
    """Worst measured gap from a failed call to message availability."""
    values = [
        r["delay_s"]
        for r in provider_error_delays(session, job_ids)
        if r["delay_s"] is not None and r["delay_s"] >= 0
    ]
    return max(values) if values else None


def max_regenerations_per_shot(session: Session, job_ids: list[str] | None = None) -> int | None:
    only, params = _only("s.job_id", job_ids)
    return session.execute(
        text(
            "SELECT max(n) - 1 FROM ("
            "SELECT count(*) AS n FROM attempts a JOIN job_shots s ON s.id = a.job_shot_id "
            "WHERE 1 = 1" + only + " GROUP BY a.job_shot_id, a.round)"
        ),
        params,
    ).scalar()


def max_shots_dropped_per_video(session: Session, job_ids: list[str] | None = None) -> int | None:
    only, params = _only("j.id", job_ids)
    return session.execute(
        text(
            "SELECT max(dropped) FROM ("
            "SELECT (SELECT count(*) FROM job_shots s "
            "WHERE s.job_id = j.id AND s.failure_reason = 'flagged_every_attempt') AS dropped "
            "FROM jobs j WHERE j.video_key IS NOT NULL" + only + ")"
        ),
        params,
    ).scalar()


def max_cut_error_s(session: Session, job_ids: list[str] | None = None) -> float | None:
    only, params = _only("job_id", job_ids)
    return session.execute(
        text("SELECT max(abs(error_s)) FROM cut_checks WHERE 1 = 1" + only), params
    ).scalar()
