"""evals report: turn a (filled) reviewer sheet and the job tables into a text report."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from sqlalchemy import select

from app.comparison.models import CutCheck
from app.db.base import session_scope
from app.db.schema import init_db
from app.evals.shoots import SHOOTS_FILE
from app.jobs.models import Job

YES = {"yes", "y", "x"}


def _yes(row: dict, column: str) -> bool:
    return (row.get(column) or "").strip().lower() in YES


def _minutes(job: Job | None) -> float | None:
    if not (job and job.first_submitted_at and job.first_finished_at):
        return None
    start = datetime.fromisoformat(job.first_submitted_at)
    return (datetime.fromisoformat(job.first_finished_at) - start).total_seconds() / 60


def _status(job: Job | None) -> str:
    if job is None:
        return "not found"
    return f"stopped ({job.stop_reason})" if job.status == "stopped" else job.status


def _unassembled(job: Job | None) -> bool:
    return job is not None and job.status == "stopped" and not job.video_key


def _cut(seconds: float | None) -> str:
    return "—" if seconds is None else f"{seconds:.3f} s"


def _count(rows: list[dict], column: str) -> str:
    return str(sum(_yes(row, column) for row in rows))


def _of(rows: list[dict], column: str) -> str:
    return f"{_count(rows, column)} of {len(rows)}" if rows else "—"


RESULTS_HEADING = "## Results on the 12 test shoots"
RUN_COMMAND = "python -m app.evals all --folder ../test-shoots --yes"


def _delivered(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["kind"] == "attempt" and _yes(r, "in_video")]


MARKS = {
    "attempt": ["visibly_ai", "room_changed", "movement_matches", "transition_matches"],
    "plan": ["text_followed"],
    "reproduction": ["looks_like_reference"],
}


def unreviewed(rows: list[dict]) -> list[dict]:
    """Rows (delivered shots, plans, reproductions) with a mark the sheet asks for still blank."""
    return [
        r
        for r in rows
        if (r["kind"] != "attempt" or _yes(r, "in_video"))
        and any(not (r.get(m) or "").strip() for m in MARKS.get(r["kind"], []))
    ]


EV1_VIDEOS = 12


def _expected_shoots(sheets: list[Path]) -> set[str]:
    """The test shoots imported for these sheets' run (shoots.json sits above the run folder)."""
    try:
        return set(json.loads((sheets[0].parent.parent / SHOOTS_FILE).read_text()))
    except (OSError, ValueError):
        return set()


def readme_blocker(rows: list[dict], sheets: list[Path]) -> str | None:
    """Why the README must not be filled from these rows, if so."""
    delivered = {r["job_id"] for r in _delivered(rows)}
    if not delivered:
        return "the sheet has no delivered videos"
    if any(r.get("providers") != "real" for r in rows):
        return "the sheets were not all made against real providers"
    reproduced = {r["job_id"] for r in rows if r["kind"] == "reproduction"}
    ev1 = [r for r in rows if r["kind"] == "plan" and r["job_id"] not in reproduced]
    done = {r["job_id"] for r in ev1} & delivered
    if len(done) < EV1_VIDEOS:
        return f"only {len(done)} EV-1 videos were delivered; {EV1_VIDEOS} are needed"
    if missing := _expected_shoots(sheets) - {r["shoot"] for r in ev1}:
        return f"EV-1 has no video for {', '.join(sorted(missing))}"
    if not reproduced:
        return "no EV-2 reproduction is on the sheets"
    if blank := unreviewed(rows):
        return f"{len(blank)} rows are not reviewed yet"
    return None


def _cuts(session, job_ids: list[str]) -> dict[str, list[tuple[str, float | None]]]:
    found: dict[str, list[tuple[str, float | None]]] = {}
    for job_id, transition, error in session.execute(
        select(CutCheck.job_id, CutCheck.transition, CutCheck.error_s).where(
            CutCheck.job_id.in_(job_ids)
        )
    ):
        found.setdefault(job_id, []).append((transition, error))
    return found


def _job_cuts(cuts: list[tuple[str, float | None]], group: list[dict]) -> tuple[float | None, bool]:
    """(worst error, VR-2 failed): a plain cut with no measurement, or none at all, fails."""
    worst = max((abs(e) for _, e in cuts if e is not None), default=None)
    shots = {r["position"] for r in group if r["kind"] == "attempt"}
    return worst, any(e is None and t == "cut" for t, e in cuts) or (not cuts and len(shots) > 1)


def _cut_cell(summaries: list[tuple[float | None, bool]]) -> str:
    worst = max((w for w, _ in summaries if w is not None), default=None)
    return f"{_cut(worst)}, cut not measured" if any(f for _, f in summaries) else _cut(worst)


def render(rows: list[dict]) -> str:
    videos: dict[str, list[dict]] = {}
    for row in rows:
        videos.setdefault(row["job_id"], []).append(row)
    with session_scope() as session:
        found = session.scalars(select(Job).where(Job.id.in_(list(videos))))
        jobs = {job.id: job for job in found}
        cuts = _cuts(session, list(videos))
    summary = {job_id: _job_cuts(cuts.get(job_id, []), group) for job_id, group in videos.items()}
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
    for job_id, group in videos.items():
        first = group[0]
        delivered = _delivered(group)
        minutes = _minutes(jobs.get(job_id))
        if minutes is not None:
            times.append(minutes)
        cells = [
            first["video"],
            first["shoot"],
            first["style"],
            job_id,
            _status(jobs.get(job_id)),
            _count(delivered, "visibly_ai"),
            _count(delivered, "room_changed"),
            _count(delivered, "movement_matches"),
            _count(delivered, "transition_matches"),
            "not assembled" if _unassembled(jobs.get(job_id)) else _cut_cell([summary[job_id]]),
            "—" if minutes is None else f"{minutes:.1f} min",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", f"Median job time: {f'{median(times):.1f} min' if times else '—'}"]
    lines += ["", "## Stopped jobs", ""]
    stopped = [
        f"- Video {group[0]['video']} ({group[0]['shoot']}): {job.stop_reason}"
        for job_id, group in videos.items()
        if (job := jobs.get(job_id)) and job.status == "stopped"
    ]
    lines += stopped or ["None."]
    lines += [
        "",
        "## Styles",
        "",
        "| Style | Reproductions like the reference | Plans text followed"
        " | Movement matches | Transition matches | Worst cut error |",
        "|---|---|---|---|---|---|",
    ]
    styles: dict[str, list[dict]] = {}
    for row in rows:
        styles.setdefault(row["style"], []).append(row)
    for style, group in styles.items():
        reproductions = [r for r in group if r["kind"] == "reproduction"]
        plans = [r for r in group if r["kind"] == "plan"]
        delivered = _delivered(group)
        cells = [
            style,
            _of(reproductions, "looks_like_reference"),
            _of(plans, "text_followed"),
            _of(delivered, "movement_matches"),
            _of(delivered, "transition_matches"),
            _cut_cell([summary[r["job_id"]] for r in plans]),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    failed = [
        r
        for r in rows
        if r["kind"] == "attempt"
        and r.get("clip_key", "x").strip()
        and (_yes(r, "visibly_ai") or _yes(r, "room_changed"))
    ]
    caught = sum(_yes(r, "flagged") for r in failed)
    lines += [
        "",
        "## Quality check (QC-1)",
        "",
        f"Attempts the reviewer failed that the check flagged: {caught} of {len(failed)} caught",
        "",
        "## Unreviewed",
        "",
    ]
    lines += [
        f"- Video {r['video']} ({r['shoot']}), {r['kind']} {r.get('position') or ''}: marks blank"
        for r in unreviewed(rows)
    ] or ["None."]
    return "\n".join(lines) + "\n"


REQUIRED = ["kind", "job_id", "in_video", *dict.fromkeys(m for ms in MARKS.values() for m in ms)]


def read_sheets(sheets: list[Path]) -> list[dict]:
    rows = []
    for sheet in sheets:
        with open(sheet, newline="", encoding="utf-8-sig") as handle:
            found = csv.DictReader(handle)
            if lacking := [c for c in REQUIRED if c not in (found.fieldnames or [])]:
                raise SystemExit(f"{sheet} has no {', '.join(lacking)} column.")
            rows += list(found)
    return rows


def fill_readme(readme: Path, report: str, sheets: list[Path]) -> None:
    """Replaces the body of the README's results section with the report's tables."""
    head, found, rest = readme.read_text().partition(RESULTS_HEADING)
    if not found:
        raise SystemExit(f"{readme} has no {RESULTS_HEADING!r} section.")
    after = rest.find("\n## ")
    tail = rest[after:] if after >= 0 else ""
    body = report.removeprefix("# Evals report\n\n").replace("\n## ", "\n### ")
    body = body.replace("## ", "### ", 1)
    names = ", ".join(f"`{s.parent.name}/{s.name}`" for s in sheets)
    intro = (
        f"Paid run by `{RUN_COMMAND}`, reported {datetime.now(UTC):%Y-%m-%d} UTC"
        f" from the reviewer sheets {names}."
    )
    readme.write_text(f"{head}{RESULTS_HEADING}\n\n{intro}\n\n{body.rstrip()}\n{tail}")


def write_report(sheets: list[Path], readme: Path | None = None) -> Path:
    """Writes a new report file beside the first sheet and returns its path. The README's
    results section is filled only when every delivered shot has been reviewed."""
    init_db()
    rows = read_sheets(sheets)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = sheets[0].parent / f"report-{stamp}.md"
    path.write_text(report := render(rows))
    if readme and not readme_blocker(rows, sheets):
        fill_readme(readme, report, sheets)
    return path
