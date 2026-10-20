"""evals report: turn a (filled) reviewer sheet and the job tables into a text report."""

import csv
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from sqlalchemy import func, select

from app.comparison.models import CutCheck
from app.db.base import session_scope
from app.db.schema import init_db
from app.jobs.models import Job

YES = {"yes", "y", "x"}


def _yes(row: dict, column: str) -> bool:
    return row[column].strip().lower() in YES


def _minutes(job: Job | None) -> float | None:
    if not (job and job.first_submitted_at and job.first_finished_at):
        return None
    start = datetime.fromisoformat(job.first_submitted_at)
    return (datetime.fromisoformat(job.first_finished_at) - start).total_seconds() / 60


def _status(job: Job | None) -> str:
    if job is None:
        return "not found"
    return f"stopped ({job.stop_reason})" if job.status == "stopped" else job.status


def _cut(seconds: float | None) -> str:
    return "—" if seconds is None else f"{seconds:.3f} s"


def _count(rows: list[dict], column: str) -> str:
    return str(sum(_yes(row, column) for row in rows))


def _of(rows: list[dict], column: str) -> str:
    return f"{_count(rows, column)} of {len(rows)}" if rows else "—"


def render(rows: list[dict]) -> str:
    videos: dict[int, list[dict]] = {}
    for row in rows:
        videos.setdefault(int(row["video"]), []).append(row)
    job_ids = [group[0]["job_id"] for group in videos.values()]
    with session_scope() as session:
        jobs = {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(job_ids)))}
        worst = dict(
            session.execute(
                select(CutCheck.job_id, func.max(func.abs(CutCheck.error_s)))
                .where(CutCheck.job_id.in_(job_ids))
                .group_by(CutCheck.job_id)
            ).all()
        )
    lines = [
        "# Evals report",
        "",
        "## Videos",
        "",
        "| Video | Shoot | Style | Job | Status | Visibly AI shots | Rooms changed"
        " | Movement matches | Transition matches | Worst cut error | Job time |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    times = []
    for video, group in videos.items():
        first = group[0]
        job = jobs.get(first["job_id"])
        delivered = [r for r in group if r["kind"] == "attempt" and _yes(r, "in_video")]
        minutes = _minutes(job)
        if minutes is not None:
            times.append(minutes)
        cells = [
            str(video),
            first["shoot"],
            first["style"],
            first["job_id"],
            _status(job),
            _count(delivered, "visibly_ai"),
            _count(delivered, "room_changed"),
            _count(delivered, "movement_matches"),
            _count(delivered, "transition_matches"),
            _cut(worst.get(first["job_id"])),
            "—" if minutes is None else f"{minutes:.1f} min",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", f"Median job time: {f'{median(times):.1f} min' if times else '—'}"]
    lines += ["", "## Stopped jobs", ""]
    stopped = [
        f"- Video {video} ({group[0]['shoot']}): {job.stop_reason}"
        for video, group in videos.items()
        if (job := jobs.get(group[0]["job_id"])) and job.status == "stopped"
    ]
    lines += stopped or ["None."]
    lines += [
        "",
        "## Styles",
        "",
        "| Style | Reproductions like the reference | Plans text followed | Worst cut error |",
        "|---|---|---|---|",
    ]
    styles: dict[str, list[dict]] = {}
    for row in rows:
        styles.setdefault(row["style"], []).append(row)
    for style, group in styles.items():
        reproductions = [r for r in group if r["kind"] == "reproduction"]
        plans = [r for r in group if r["kind"] == "plan"]
        errors = [worst[r["job_id"]] for r in plans if worst.get(r["job_id"]) is not None]
        cells = [
            style,
            _of(reproductions, "looks_like_reference"),
            _of(plans, "text_followed"),
            _cut(max(errors, default=None)),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    failed = [
        r
        for r in rows
        if r["kind"] == "attempt" and (_yes(r, "visibly_ai") or _yes(r, "room_changed"))
    ]
    caught = sum(_yes(r, "flagged") for r in failed)
    lines += [
        "",
        "## Quality check (QC-1)",
        "",
        f"Attempts the reviewer failed that the check flagged: {caught} of {len(failed)} caught",
    ]
    return "\n".join(lines) + "\n"


def write_report(sheet: Path) -> Path:
    """Writes a new report file beside the sheet and returns its path."""
    init_db()
    with open(sheet, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = sheet.parent / f"report-{stamp}.md"
    path.write_text(render(rows))
    return path
