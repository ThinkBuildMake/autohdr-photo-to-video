"""Read-only queries behind the metrics report. Each returns a number, or None with no rows."""

from statistics import median

from sqlalchemy import text
from sqlalchemy.orm import Session

_SECONDS = 86400.0


def _waits(session: Session) -> list[float]:
    rows = session.execute(
        text(
            "SELECT (julianday(first_finished_at) - julianday(first_submitted_at)) * :day "
            "FROM jobs WHERE first_submitted_at IS NOT NULL AND first_finished_at IS NOT NULL"
        ),
        {"day": _SECONDS},
    )
    return [row[0] for row in rows]


def slowest_wait_s(session: Session) -> float | None:
    waits = _waits(session)
    return max(waits) if waits else None


def typical_wait_s(session: Session) -> float | None:
    waits = _waits(session)
    return median(waits) if waits else None


def provider_error_to_user_s(session: Session) -> float | None:
    """Worst gap from a failed provider call to the moment the user could be told."""
    return session.execute(
        text(
            "SELECT max((julianday(COALESCE(a.finished_at, j.finished_at)) "
            "- julianday(c.finished_at)) * :day) "
            "FROM provider_calls c "
            "LEFT JOIN attempts a ON a.id = c.attempt_id "
            "LEFT JOIN jobs j ON j.id = c.job_id AND j.status = 'stopped' "
            "WHERE c.status = 'error' AND c.finished_at IS NOT NULL "
            "AND COALESCE(a.finished_at, j.finished_at) IS NOT NULL"
        ),
        {"day": _SECONDS},
    ).scalar()


def max_regenerations_per_shot(session: Session) -> int | None:
    return session.execute(
        text(
            "SELECT max(n) - 1 FROM ("
            "SELECT count(*) AS n FROM attempts GROUP BY job_shot_id, round)"
        )
    ).scalar()


def max_shots_dropped_per_video(session: Session) -> int | None:
    return session.execute(
        text(
            "SELECT max(dropped) FROM ("
            "SELECT (SELECT count(*) FROM job_shots s "
            "WHERE s.job_id = j.id AND s.failure_reason = 'flagged_every_attempt') AS dropped "
            "FROM jobs j WHERE j.video_key IS NOT NULL)"
        )
    ).scalar()


def max_cut_error_s(session: Session) -> float | None:
    return session.execute(text("SELECT max(abs(error_s)) FROM cut_checks")).scalar()
