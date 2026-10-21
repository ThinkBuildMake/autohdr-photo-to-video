"""evals run: create and submit a suite's jobs, wait for them, write the reviewer sheet."""

import csv
import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.base import session_scope
from app.db.schema import init_db
from app.errors import AppError
from app.evals.report import write_report
from app.evals.shoots import SHOOTS_FILE
from app.files import service as files
from app.jobs import drafts, queue
from app.jobs.models import Attempt, Job, JobShot
from app.jobs.schemas import JobCreate
from app.library import service as library

FINISHED = {"ready", "ready_with_failures", "stopped"}
POLL_S = 30
SHEET_FILE = "sheet.csv"
JUDGMENTS = ["visibly_ai", "room_changed", "movement_matches", "transition_matches"]
COLUMNS = [
    "kind",
    "video",
    "shoot",
    "style",
    "job_id",
    "providers",
    "position",
    "round",
    "attempt",
    "flagged",
    "in_video",
    "clip_key",
    "clip_link",
    "plan_text",
    "reference_key",
    "reference_link",
    "note",
    *JUDGMENTS,
    "text_followed",
    "looks_like_reference",
]


@dataclass
class RunJob:
    video: int
    shoot: str
    job_id: str
    note: str = ""
    timed_out: bool = False


def _style(name: str):
    for summary in library.list_styles():
        if summary.name == name:
            return library.get_style(summary.id)
    raise SystemExit(f"No style named {name!r}.")


def _job(job_id: str):
    """The job, or None when it is gone (the sheet then carries a note instead of stopping)."""
    try:
        return queue.get_job(job_id)
    except AppError:
        return None


def _wait(jobs: list[RunJob], done, deadline: float) -> bool:
    """Polls until done(job) holds for each of the jobs (a missing job counts as done)."""
    while not all((job := _job(run.job_id)) is None or done(job) for run in jobs):
        if time.monotonic() > deadline:
            return False
        time.sleep(POLL_S)
    return True


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _attempt_rows(base: dict) -> list[dict]:
    """One row per attempt, flagged ones and ones that made no clip included."""
    with session_scope() as session:
        found = session.execute(
            select(
                JobShot.position,
                JobShot.status.label("shot_status"),
                JobShot.removed,
                JobShot.final_attempt_id,
                Attempt.id,
                Attempt.round,
                Attempt.attempt_no,
                Attempt.status,
                Attempt.clip_key,
            )
            .join(Attempt, Attempt.job_shot_id == JobShot.id)
            .where(JobShot.job_id == base["job_id"])
            .order_by(JobShot.position, Attempt.round, Attempt.attempt_no)
        ).all()
    return [
        {
            **base,
            "kind": "attempt",
            "position": row.position,
            "round": row.round,
            "attempt": row.attempt_no,
            "flagged": _yes(row.status == "flagged"),
            "in_video": _yes(
                row.final_attempt_id == row.id and row.shot_status == "passed" and not row.removed
            ),
            "clip_key": row.clip_key or "",
            "clip_link": files.presign_download(row.clip_key) if row.clip_key else "",
        }
        for row in found
    ]


def _video_key(job_id: str | None) -> str:
    if job_id is None:
        return ""
    with session_scope() as session:
        return session.scalar(select(Job.video_key).where(Job.id == job_id)) or ""


def _link(key: str) -> str:
    return files.presign_download(key) if key else ""


def _rows(jobs: list[RunJob], style, purpose: str) -> list[dict]:
    reference_key = _video_key(style.reference_job_id) if purpose == "reproduction" else ""
    providers = "fake" if get_settings().FAKE_PROVIDERS else "real"
    rows = []
    for job in jobs:
        base = {
            "video": job.video,
            "shoot": job.shoot,
            "style": style.name,
            "job_id": job.job_id,
            "providers": providers,
        }
        try:
            key = _video_key(job.job_id)
            video = {
                **base,
                "clip_key": key,
                "clip_link": _link(key),
                "plan_text": style.style_text,
                "note": job.note,
            }
            more = [{**video, "kind": "plan"}]
            if purpose == "reproduction":
                more.append(
                    {
                        **video,
                        "kind": "reproduction",
                        "reference_key": reference_key,
                        "reference_link": _link(reference_key),
                    }
                )
            rows += more + _attempt_rows(base)
        except Exception as error:  # keep the job id so `links` and `report` can resume
            rows.append({**base, "kind": "plan", "note": f"rows could not be built: {error}"})
    return rows


def _write_sheet(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as handle:
        extra = [key for row in rows for key in row if key not in COLUMNS]
        writer = csv.DictWriter(handle, fieldnames=[*COLUMNS, *dict.fromkeys(extra)], restval="")
        writer.writeheader()
        writer.writerows(rows)


def _create_jobs(jobs: list[RunJob], shoots: dict[str, str], style, purpose: str) -> None:
    """Appends one job per shoot to `jobs` as each is created, so none is lost on an error."""
    for video, (label, photoshoot_id) in enumerate(shoots.items(), start=1):
        body = JobCreate(
            photoshoot_id=photoshoot_id,
            style_text=style.style_text,
            song_id=style.song.id,
            style_id=style.id,
            purpose=purpose,
        )
        jobs.append(RunJob(video, label, drafts.create_job(body).id))


def _submit_planned(jobs: list[RunJob], deadline: float) -> list[RunJob]:
    """Waits for each shot plan; submits the ready ones and notes why the others are skipped."""
    _wait(jobs, lambda job: job.plan_status != "planning", deadline)
    submitted = []
    for run_job in jobs:
        job = _job(run_job.job_id)
        if job is None:
            run_job.note = "skipped: the job is missing"
        elif job.plan_status == "planning":
            run_job.note, run_job.timed_out = "skipped: the shot plan was not ready in time", True
        elif job.plan_status == "failed":
            run_job.note = f"skipped: the shot plan failed: {job.plan_notes}"
        else:
            try:
                queue.submit_job(run_job.job_id)
                submitted.append(run_job)
            except AppError as error:
                run_job.note = f"skipped: {error.message}"
    return submitted


def run_suite(suite: str, style_name: str, out: Path, timeout_min: float = 480) -> Path:
    """Returns the new run folder; exits non-zero (after writing the sheet) on a timeout."""
    init_db()
    style = _style(style_name)
    shoots_file = out / SHOOTS_FILE
    if not shoots_file.exists():
        raise SystemExit(f"No {shoots_file}: run `evals import --out {out}` first.")
    shoots = json.loads(shoots_file.read_text())
    purpose = "video" if suite == "ev1" else "reproduction"
    if suite == "ev2":
        if style.reference_job_id is None:
            raise SystemExit(f"Style {style.name!r} has no reference video: mark one first.")
        shoots = {k: v for k, v in shoots.items() if v != style.demo_photoshoot_id}
        shoots = dict(list(shoots.items())[:2])
    deadline = time.monotonic() + timeout_min * 60
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    slug = re.sub(r"[^a-z0-9]+", "-", style.name.lower()).strip("-")
    folder = out / f"{suite}-{slug}-{stamp}-{secrets.token_hex(2)}"
    folder.mkdir(parents=True)
    jobs: list[RunJob] = []
    finished = False
    try:
        _create_jobs(jobs, shoots, style, purpose)
        submitted = _submit_planned(jobs, deadline)
        _wait(submitted, lambda job: job.status in FINISHED, deadline)
        for run_job in submitted:
            job = _job(run_job.job_id)
            if job is None:
                run_job.note = "the job is missing"
            elif job.status not in FINISHED:
                run_job.note, run_job.timed_out = "not finished before the timeout", True
        finished = True
    finally:
        # The paid jobs outlive this process: always leave a sheet naming every one of them.
        if not finished:
            for run_job in jobs:
                run_job.note = run_job.note or "interrupted: the run stopped before this finished"
        _write_sheet(folder / SHEET_FILE, _rows(jobs, style, purpose))
        if not finished:
            print(f"reviewer sheet (run stopped early): {folder / SHEET_FILE}")
    write_report([folder / SHEET_FILE])
    if any(job.timed_out for job in jobs):
        raise SystemExit(f"Timed out after {timeout_min:g} minutes; sheet in {folder}.")
    return folder


def relink_sheet(sheet: Path) -> Path:
    """Copies the sheet beside it with fresh links (they last 1 hour; review takes longer)."""
    with open(sheet, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["clip_link"] = _link(row.get("clip_key", ""))
        row["reference_link"] = _link(row.get("reference_key", ""))
    fresh = sheet.with_name(f"{sheet.stem.removesuffix('-relinked')}-relinked{sheet.suffix}")
    _write_sheet(fresh, rows)
    return fresh
