"""The metrics report: one panel per guarantee metric in KEY_METRICS.md, in that order."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.metrics import queries

NO_DATA = "no data yet"


def _minutes(seconds: float) -> str:
    return f"{seconds / 60:.1f} min"


def _seconds(seconds: float) -> str:
    return f"{seconds:.1f} s"


def _cut_seconds(seconds: float) -> str:
    return f"{seconds:.3f} s"


def _count(value: float) -> str:
    return str(int(value))


@dataclass(frozen=True)
class Panel:
    title: str
    requirement: str
    threshold: str
    query: Callable[..., float | None]
    fmt: Callable[[float], str]


PANELS = (
    Panel(
        "Video wait time (slowest)",
        "PF-1",
        "<= 30 min from submit to playable, including regeneration",
        queries.slowest_wait_s,
        _minutes,
    ),
    Panel(
        "Video wait time (typical)",
        "PF-2",
        "median <= 10 min",
        queries.typical_wait_s,
        _minutes,
    ),
    Panel(
        "Time to tell the user about a provider error",
        "RL-1",
        "<= 60 s from the error",
        queries.provider_error_to_user_s,
        _seconds,
    ),
    Panel(
        "Regeneration attempts per shot",
        "QC-2",
        "<= 3 before the shot is reported failed",
        queries.max_regenerations_per_shot,
        _count,
    ),
    Panel(
        "Shots dropped because every attempt was flagged",
        "VR-1 (proxy)",
        "<= 2 per video, target 0",
        queries.max_shots_dropped_per_video,
        _count,
    ),
    Panel(
        "Cut-time error against the style",
        "VR-2",
        "<= 0.1 s per cut",
        queries.max_cut_error_s,
        _cut_seconds,
    ),
)


def render_report(session: Session, job_ids: list[str] | None = None) -> str:
    blocks = []
    for panel in PANELS:
        value = panel.query(session, job_ids)
        shown = NO_DATA if value is None else panel.fmt(value)
        blocks.append(
            f"{panel.title}\n"
            f"  Requirement: {panel.requirement}\n"
            f"  Threshold:   {panel.threshold}\n"
            f"  Value:       {shown}\n"
        )
        if panel.requirement == "RL-1":
            rows = queries.provider_error_delays(session, job_ids)
            if rows:
                blocks[-1] += (
                    "  Per-error persisted message availability "
                    "(browser polling measured separately):\n"
                )
            for row in rows:
                delay = row["delay_s"]
                shown = _seconds(delay) if delay is not None and delay >= 0 else "unmeasured"
                blocks[-1] += (
                    f"    call={row['call_id']} job={row['job_id'] or '-'} "
                    f"shot={row['job_shot_id'] or '-'} attempt={row['attempt_id'] or '-'} "
                    f"error={row['error_kind'] or 'unknown'}: {shown}\n"
                )
    return "\n".join(blocks)
